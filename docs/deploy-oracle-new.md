# Deploying to the `oracle-new` VPS

ImovelRadar runs at `https://radar.leilaolabs.com.br` on the `oracle-new` VPS,
sharing the host with the `caixa-auction` stack. Design rationale lives in
[`docs/superpowers/specs/2026-08-12-deploy-oracle-new-design.md`](superpowers/specs/2026-08-12-deploy-oracle-new-design.md).

## How the two stacks fit together

```
internet :443 ──▶ nginx (owned by the caixa-auction stack)
                    ├─ api.leilaolabs.com.br   → crawler:8000           [caixa-auction_default]
                    └─ radar.leilaolabs.com.br → imovel-radar-web:8000  [edge]

[imovel-radar_default] (private)   web ↔ postgres:16
```

`edge` is an external Docker network shared by the two projects. ImovelRadar
publishes **no** host port for the app — `crawler` already owns `0.0.0.0:8000`.
Postgres stays on `127.0.0.1:5433` for SSH-tunnel debugging.

TLS, the vhost and the basic-auth gate on `/upload` live in the **caixa-auction**
repo (`infra/nginx/`), because that is where nginx lives.

## Layout on the host

| Path | What |
| --- | --- |
| `~/apps/imovel-radar` | this repo |
| `~/apps/imovel-radar/.env` | production env (never committed) |
| `~/apps/caixa-auction/infra/nginx/custom-templates/radar.*.template` | the vhost |
| `~/apps/caixa-auction/infra/nginx/secrets/radar.htpasswd` | basic-auth users |

## Routine deploy

```bash
ssh oracle-new
cd ~/apps/imovel-radar
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f web
```

Migrations run automatically from the entrypoint (`alembic upgrade head`).

Because every command needs both files, it is worth exporting once per shell:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
docker compose up -d
```

## First-time setup

Only needed once; kept here so the setup is reproducible.

**1. Shared network**

```bash
docker network create edge
```

**2. Clone and configure**

```bash
git clone git@github.com:tqchagas/imovel-radar.git ~/apps/imovel-radar
cd ~/apps/imovel-radar
cp .env.example .env
# then edit .env: strong POSTGRES_PASSWORD, and mirror it into DATABASE_URL
```

**3. Seed the database from a local dump**

On the workstation:

```bash
docker compose exec -T postgres pg_dump -U imovelradar -Fc imovelradar > imovelradar.dump
scp imovelradar.dump oracle-new:~/
```

On the VPS, before the first `web` start:

```bash
cd ~/apps/imovel-radar
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U imovelradar -d imovelradar --no-owner --no-privileges < ~/imovelradar.dump
```

The dump carries `alembic_version`, so the first `alembic upgrade head` is a no-op.

**4. Basic-auth credentials for `/upload`**

```bash
cd ~/apps/caixa-auction
mkdir -p infra/nginx/secrets
docker run --rm httpd:alpine htpasswd -nbB <user> '<password>' \
  > infra/nginx/secrets/radar.htpasswd
chmod 600 infra/nginx/secrets/radar.htpasswd
```

**5. DNS, vhost and certificate**

Point `radar.leilaolabs.com.br` at the VPS in Cloudflare, then:

```bash
cd ~/apps/caixa-auction
echo 'RADAR_DOMAIN=radar.leilaolabs.com.br' >> .env
docker compose up -d nginx            # renders the HTTP-only vhost (no cert yet)

docker compose run --rm certbot certonly --webroot -w /var/www/certbot \
  -d radar.leilaolabs.com.br --email <you@example.com> --agree-tos --no-eff-email

docker compose restart nginx          # cert now exists → HTTPS vhost renders
```

Renewal is handled by whatever already renews `api.leilaolabs.com.br`.

## Verifying

```bash
curl -s https://radar.leilaolabs.com.br/health                      # {"status":"ok"}
curl -sI https://radar.leilaolabs.com.br/upload | head -1           # 401
curl -sI https://radar.leilaolabs.com.br/enviar | head -1           # 401
curl -sI 'https://radar.leilaolabs.com.br/stats/neighborhoods' \
  | grep -i x-cache-status                                          # MISS, then HIT
```

## Operations

**Logs**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f web
docker logs -f caixa-auction-nginx-1
```

**psql from the workstation**

```bash
ssh -L 5433:127.0.0.1:5433 oracle-new
psql "postgresql://imovelradar:<password>@127.0.0.1:5433/imovelradar"
```

**Purge the nginx cache** (60s TTL means you rarely need to)

```bash
docker exec caixa-auction-nginx-1 sh -c 'rm -rf /var/cache/nginx/radar/*'
docker exec caixa-auction-nginx-1 nginx -s reload
```

## Gotchas

- Changing `POSTGRES_PASSWORD` after the volume exists does not change the actual
  database password. Change it inside Postgres with `ALTER ROLE`, then update `.env`.
- Recreating the caixa-auction nginx container restarts TLS for **every** site on
  the host, including `api.leilaolabs.com.br`. It is a few seconds, but not free.
- `docker compose up -d` without the prod overlay will republish port 8000 and
  fail against `crawler`. Use `COMPOSE_FILE` so you cannot forget.
