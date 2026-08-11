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

The app will be available at `http://localhost:8000` and the API docs at
`http://localhost:8000/docs`.

> Note: `docker-compose.yml` maps Postgres to host port **5433** (not 5432) to
> avoid clashing with a locally installed Postgres server. The `web` service uses
> an internal connection string, so `.env` is only needed for local development
> or optional variables like `QUINTOANDAR_PRICE_SUGGESTION_COOKIE`.

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
| `/enviar` | Upload do CSV de ITBI |
| `/estilo` | O design system (cor, tipografia, controles, princípios) |

Filtros de busca aceitam cidade, bairro, rua, número, faixa de valor, área,
tipo de construção/ocupação e data — todos refletidos na URL, então qualquer
busca é compartilhável. Links antigos no formato `/?street=X` continuam
funcionando: a home redireciona para `/busca` preservando a query.

## Ingesting data

### Via web interface

Use `http://localhost:8000/enviar` to send an ITBI CSV export.

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
- `POST /upload` — upload an ITBI CSV file (`city` form field + `file`)

## Tests

```bash
pytest -v
```

For Docker-based tests, run them inside the `web` container:

```bash
docker compose exec web pytest -v
```
