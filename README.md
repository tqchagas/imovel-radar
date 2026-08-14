# ImovelRadar

Public dataset + API of Brazilian real-estate transactions, sourced from ITBI
(property transfer tax) open data published by city councils. Settled ITBI
implies a real transaction at a real declared value — the goal is to use this
as a price signal. Coverage is limited to cities that publish this data openly.

Currently covered: **Belo Horizonte (MG)**.

## Quick start (Docker)

The easiest way to run the project is with Docker Compose. It builds the API
image, runs Postgres, applies migrations, and starts the server:

```bash
cp .env.example .env
docker compose up --build
```

The app will be available at `http://127.0.0.1:8000` and the API docs at
`http://127.0.0.1:8000/docs`.

### Docker layout (multi-project / VPS-friendly)

This stack is only `web` + `postgres` (no reverse proxy in this repo). Defaults
are safe to run next to other Compose projects on the same machine:

| Concern | Default |
| --- | --- |
| App port on host | `127.0.0.1:8000` (`WEB_PORT`) |
| Postgres port on host | `127.0.0.1:5433` (`POSTGRES_PORT`) — not 5432 |
| Bind addresses | localhost only (not published on `0.0.0.0`) |
| Code in container | image build only (no `.:/app` mount) |
| DB credentials | `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` in `.env` |
| Restart | `unless-stopped` |

Inside Compose, `web` always connects to host `postgres` (service name). The
`DATABASE_URL` in `.env` is for tools running on the **host** (local uvicorn,
Alembic outside Docker).

If another stack already uses 8000 or 5433, change `WEB_PORT` / `POSTGRES_PORT`
in `.env`. On a shared VPS, also set a strong `POSTGRES_PASSWORD` and keep a
host firewall that does not expose these ports publicly.

> Changing `POSTGRES_*` after the first successful Postgres start does **not**
> rewrite an existing data volume. For local dev you can reset with
> `docker compose down -v` (destroys DB data). On a machine with real data,
> keep the original password or migrate deliberately.

No reverse proxy is defined here on purpose — on a shared host it belongs to the
host, not to this repo. Production adds `docker-compose.prod.yml`, which drops the
published app port and joins a shared `edge` network so an external nginx can reach
the container. See [`docs/deploy-oracle-new.md`](docs/deploy-oracle-new.md).

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d postgres
PYTHONPATH=. alembic upgrade head
uvicorn app.main:app --reload
```

## Web interface

Acesse `http://localhost:8000/`. A interface tem oito telas:

| Rota | Tela |
| --- | --- |
| `/` | Início — números da base e ranking de R$/m² por bairro |
| `/busca` | Busca de quitações (tabela ou cards), com filtros e ordenação |
| `/imovel` | Histórico de uma unidade: linha do tempo e quitações |
| `/bairro` | Ranking de bairros e o detalhe de cada um |
| `/curiosidades` | Recordes e extremos da base inteira |
| `/comparar` | Até três unidades lado a lado (lista guardada no navegador) |
| `/enviar` | Upload administrativo do CSV de ITBI (protegido por Basic Auth no Nginx) |
| `/estilo` | O design system (cor, tipografia, controles, princípios) |

Filtros de busca aceitam cidade, bairro, rua, número, faixa de valor, área,
tipo de construção/ocupação e data — todos refletidos na URL, então qualquer
busca é compartilhável. Links antigos no formato `/?street=X` continuam
funcionando: a home redireciona para `/busca` preservando a query.

## Ingesting data

### Via web interface (administrativa)

Use `https://radar.leilaolabs.com.br/enviar` after authenticating with the Nginx
Basic Auth credentials. The upload page is intentionally absent from the public
navigation and the upload operation is not published in the public OpenAPI schema.
See [`docs/radar-nginx-auth.conf.example`](docs/radar-nginx-auth.conf.example) for
the proxy protection.

### Via CLI

Download Belo Horizonte's ITBI CSV export and run:

```bash
PYTHONPATH=. python -m app.ingestion.cli --city belo_horizonte --file /path/to/file.csv
```

Re-running ingestion on the same file is safe — rows are deduplicated by content
hash.

## Market comparables / price suggestions

The project can enrich market-comparable listings with price-suggestion data
from QuintoAndar. First, set the session cookie in `.env`:

```bash
QUINTOANDAR_PRICE_SUGGESTION_COOKIE=<your 5AJWT_AUTH cookie value>
```

Then run the enrichment CLI:

```bash
PYTHONPATH=. python -m app.ingestion.cli quintoandar-price-suggestions \
  --limit 100 --workers 1 --worker-index 0
```

Use `--cidade` to filter by city (can be passed multiple times). For parallel
workers, run the same command with `--worker-index` from `0` to `workers - 1`.

## Endpoints

- `GET /transactions` — filter by `city`, `neighborhood`, `min_value`,
  `max_value`, `min_area`, `max_area`, `construction_type`, `occupation_type`,
  `date_from`, `date_to`; order with `sort` (`date_desc`, `date_asc`,
  `value_desc`, `value_asc`, `m2_desc`, `m2_asc`); paginate with
  `limit`/`offset`.
- `GET /transactions/{id}`
- `GET /cities`
- `GET /neighborhoods?city=belo_horizonte`
- `GET /stats/overview`, `GET /stats/neighborhoods`,
  `GET /stats/neighborhoods/{neighborhood}`
- `GET /stats/curiosities?city=belo_horizonte` — records and extremes over the
  whole history. It is a full scan, so the result is memoized per city and
  recomputed only when the row count or the last settlement date changes.
- The administrative `POST /upload` operation is intentionally omitted from the
  public API documentation and must only be reachable through the authenticated
  Nginx location.

## Tests

```bash
pytest -v
```

For Docker-based tests, run them inside the `web` container:

```bash
docker compose exec web pytest -v
```
