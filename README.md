# ImovelRadar

Public dataset + API of Brazilian real-estate transactions, sourced from ITBI
(property transfer tax) open data published by city councils. Settled ITBI
implies a real transaction at a real declared value — the goal is to use this
as a price signal. Coverage is limited to cities that publish this data openly.

Currently covered: **Belo Horizonte (MG)**.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d postgres
PYTHONPATH=. alembic upgrade head
```

> Note: `docker-compose.yml` maps Postgres to host port **5433** (not 5432) to
> avoid clashing with a locally installed Postgres server. Adjust `.env` if you
> don't have that conflict.

## Running the API

```bash
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`.

## Ingesting data

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
  `date_from`, `date_to`; paginate with `limit`/`offset`.
- `GET /transactions/{id}`
- `GET /cities`
- `GET /neighborhoods?city=belo_horizonte`

## Tests

```bash
pytest -v
```
