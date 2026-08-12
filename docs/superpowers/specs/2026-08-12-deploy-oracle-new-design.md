# Deploy ImovelRadar to the `oracle-new` VPS

## Purpose

Put ImovelRadar on the public internet at `radar.leilaolabs.com.br`, running on the
`oracle-new` VPS next to the existing `caixa-auction` stack, seeded with the 507k
transactions already ingested locally.

The two stacks share one machine and one TLS terminator. They must not share
databases, volumes, or ports.

## Current state

### VPS `oracle-new`

Ubuntu 24.04 LTS, `aarch64`, 11 GiB RAM, 32 GiB free disk. Docker 29.7.2,
Compose v5.4.0.

One Compose project, `caixa-auction`, in `~/apps/caixa-auction` (git:
`github.com:tqchagas/caixa-auction`, and the host has working SSH auth to GitHub):

| Service | Image | Host ports |
| --- | --- | --- |
| `caixa-auction-nginx-1` | `nginx:1.27-alpine` | `0.0.0.0:80`, `0.0.0.0:443` |
| `crawler` | `caixa-auction-crawler` | `0.0.0.0:8000` |
| `calc` | `caixa-auction-calc` | none (`expose` only) |
| `caixa-auction-postgres-1` | `postgres:17` | `127.0.0.1:5432` |
| `certbot` | `certbot/certbot` | none |

Its nginx renders vhosts at container start from
`infra/nginx/custom-templates/*.template` via
`infra/nginx/99-render-conf.sh`. Optional vhosts (WAHA, CALC) follow one pattern:
gate on an env var, pick the HTTPS template when the Let's Encrypt cert exists on the
mounted `letsencrypt` volume, otherwise the HTTP-only template. Existing certs:
`api.leilaolabs.com.br`, `waha.leilaolabs.com.br`.

### ImovelRadar

FastAPI + Postgres 16. Local database is 256 MB: `transactions` (507,706 rows,
248 MB), `market_comparables` (empty), `alembic_version`.

The HTTP surface is read-only except for exactly one endpoint:
`POST /upload` (`app/api/routes/transactions.py:115`), reached from the `/enviar`
page. Everything else is `GET`. The app has no authentication of any kind and uses
no cookies or sessions.

### Conflicts to resolve

- `crawler` publishes `0.0.0.0:8000`, which collides with ImovelRadar's default
  `WEB_PORT=8000`. Binding to `127.0.0.1:8000` does not help — `0.0.0.0` already
  covers it.
- Postgres `127.0.0.1:5433` is free (caixa-auction uses 5432).
- `radar.leilaolabs.com.br` does not resolve. `leilaolabs.com.br` is on Cloudflare
  (proxied; `api` resolves to Cloudflare IPs). HTTP-01 issuance works through the
  proxy — `api` already does exactly this.

## Design

### Topology

```
internet :443 ──▶ nginx (caixa-auction)
                    ├─ api.leilaolabs.com.br   → crawler:8000            [caixa-auction_default]
                    ├─ ${CALC_DOMAIN}          → calc:8000               [caixa-auction_default]
                    ├─ ${WAHA_DOMAIN}          → waha                    [caixa-auction_default]
                    └─ radar.leilaolabs.com.br → imovel-radar-web:8000   [edge]           ← new

[imovel-radar_default] (private)   web ↔ postgres:16  ← own volume
```

`edge` is a user-created external bridge network whose only purpose is to let the
shared nginx reach app containers from other Compose projects. nginx joins both
`caixa-auction_default` and `edge`; ImovelRadar's `web` joins both
`imovel-radar_default` and `edge`. ImovelRadar's Postgres stays off `edge`, so nginx
cannot reach it.

No new host port is published for the app. This sidesteps the 8000 collision
entirely rather than renumbering around it.

### ImovelRadar: production overlay

`docker-compose.yml` stays exactly as it is — it is the dev stack, and its
`127.0.0.1` port bindings are what a developer wants. Production is a second file,
`docker-compose.prod.yml`, applied as an overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The overlay:

- Drops `web`'s published port (Compose merges `ports` by appending, so the overlay
  must reset the list to empty) and replaces it with `expose: 8000`.
- Sets `container_name: imovel-radar-web` so nginx has a stable DNS name to resolve
  on `edge`.
- Joins `web` to `edge` (declared `external: true`) and `imovel-radar_default`.
- Adds memory limits and Postgres tuning sized for a shared host.

Postgres keeps its `127.0.0.1:5433` binding in production. It is not reachable from
outside the host and it makes `psql` over an SSH tunnel possible for debugging.

Postgres settings, sized against a 256 MB dataset on a shared 11 GiB box:
`shared_buffers=256MB`, `effective_cache_size=768MB`, `work_mem=16MB`,
`maintenance_work_mem=64MB`, `max_connections=20`. Memory limits: Postgres 640 MiB,
web 512 MiB. Headroom is fine — caixa-auction reserves 768 MiB + 2 GiB + 512 MiB and
the host reports ~10 GiB available.

### nginx vhost (changes in the `caixa-auction` repo)

Two new templates following the CALC/WAHA pattern exactly, gated on `RADAR_DOMAIN`:

- `radar.http.conf.template` — port 80, ACME challenge webroot, everything else
  redirects to HTTPS. This is what renders before the cert exists.
- `radar.https.conf.template` — port 80 redirect + port 443 vhost, upstream
  `http://imovel-radar-web:8000` resolved at request time through Docker's resolver
  (`127.0.0.11`), matching how the existing vhosts do it.

`99-render-conf.sh` gets a `RADAR_DOMAIN` block copied from the `CALC_DOMAIN` block,
plus a `mkdir -p /var/cache/nginx/radar` for the new cache zone.

The nginx service in `caixa-auction/docker-compose.yml` gains: the `edge` network,
`RADAR_DOMAIN` in `environment`, and a read-only bind mount of
`./infra/nginx/secrets` for the htpasswd file.

### Auth: `/upload` and `/enviar`

The product is deliberately free and open — all read paths stay unauthenticated.
Only the two write-side paths are protected, and they are protected at the proxy:

```nginx
location = /enviar { auth_basic "ImovelRadar admin"; auth_basic_user_file /etc/nginx/secrets/radar.htpasswd; ... }
location = /upload { auth_basic "ImovelRadar admin"; auth_basic_user_file /etc/nginx/secrets/radar.htpasswd;
                     client_max_body_size 200m; proxy_read_timeout 600s; ... }
```

`=` is nginx's exact-match modifier and takes priority over every prefix and regex
location, so neither path can leak through the public blocks below them. The
generous body limit and read timeout exist because ingesting a full council CSV is a
long, large request.

The browser caches basic-auth credentials per origin, so after the operator
authenticates on `/enviar`, the page's `fetch` to `/upload` carries the header
automatically. No frontend change is needed.

The htpasswd file lives at `caixa-auction/infra/nginx/secrets/radar.htpasswd`
(bcrypt, `htpasswd -B`), gitignored, created on the VPS.

Trade-off accepted: one shared credential, browser-native prompt, no logout. If this
ever needs real accounts or an audit trail, the successor is an app-level token or
Cloudflare Access — but neither is worth building for a single operator today.

Note that the app itself remains unauthenticated. Anything with direct access to the
`edge` network or to the container could still `POST /upload`. That is acceptable:
reaching either requires host access, which is already game over.

### Caching

A dedicated `radar_api` cache zone, separate from caixa-auction's `anon_html` so the
two apps cannot evict each other:

```nginx
proxy_cache_path /var/cache/nginx/radar levels=1:2 keys_zone=radar_api:20m
                 max_size=300m inactive=1h use_temp_path=off;
```

- `/transactions`, `/properties`, `/stats`, `/curiosities` — `proxy_cache_valid 200 60s`
- `/static/` — `proxy_cache_valid 200 1h`
- `X-Cache-Status` response header for debugging.
- `proxy_cache_use_stale error timeout updating` so a slow query or a restart serves
  the last good response instead of an error.

The app sets no cookies, so no bypass rule is needed — every anonymous request is
equivalent and the query string is the cache key.

`POST` is not cached by nginx default, so `/upload` is unaffected.

### Data migration

One-shot full copy, no ongoing sync:

1. `pg_dump -Fc` the local database (schema + data + `alembic_version`), ~60–80 MB
   in custom format.
2. `scp` to the VPS.
3. Start production Postgres alone; the image creates an empty `imovelradar`
   database from `POSTGRES_*`.
4. `pg_restore --no-owner --no-privileges` into it.
5. Start `web`. Its entrypoint runs `alembic upgrade head`, which is a no-op because
   `alembic_version` came over in the dump.

Both sides run Postgres 16, so there is no version skew. Restoring before the first
`web` start avoids any race between Alembic and the restore.

### Deployment order

The DNS record and the cert must exist in that order, and the nginx cutover briefly
restarts the live proxy:

1. Create the `radar.leilaolabs.com.br` DNS record (Cloudflare, proxied).
2. Create the `edge` network; clone ImovelRadar to `~/apps/imovel-radar`; write its
   production `.env` with a strong `POSTGRES_PASSWORD`.
3. Restore the data; bring the ImovelRadar stack up; verify from inside the VPS.
4. Create the htpasswd file.
5. Apply the caixa-auction changes with `RADAR_DOMAIN` set and recreate nginx — HTTP
   template renders (no cert yet). **This restarts the live proxy for a few
   seconds.**
6. Run certbot for the new domain; restart nginx so the HTTPS template renders.
7. Verify: public reads work, `/upload` and `/enviar` return 401 without
   credentials.

## Out of scope

- Automated deploys / CI. Deployment is `git pull` + `docker compose up -d --build`.
- Backups of the production database. Worth doing, but a separate concern from
  standing the service up; caixa-auction already has a `~/backups` convention to
  follow later.
- Ongoing local→prod data sync. Future ingests go through `/upload` in production.
- Moving `crawler` off its public `0.0.0.0:8000` binding. It is pre-existing and
  unrelated, and the design routes around it.
- App-level auth, user accounts, rate limiting.
