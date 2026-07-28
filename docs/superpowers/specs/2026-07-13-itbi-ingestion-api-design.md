# ImovelRadar — ITBI Ingestion & Query API (MVP)

## Purpose

Public repo showing real-estate price signals in Brazil, derived from ITBI (property
transfer tax) records that city councils publish as open data. ITBI settlement implies
a real transaction happened at a real declared value — a strong signal for price
estimation, which is the longer-term goal of the project. This spec covers the MVP:
getting one city's data reliably ingested and queryable via a FastAPI backend. Price
estimation is explicitly out of scope for this phase.

Coverage is limited to Brazilian cities whose councils publish ITBI open data
(CSV/XLSX/JSON dumps). First target: **Belo Horizonte (MG)**.

## Scope

**In scope:**
- Ingest Belo Horizonte's ITBI CSV export into a normalized `transactions` table.
- Multi-city-ready design (adapter pattern) even though only BH is implemented now.
- Read-only, filterable, paginated FastAPI endpoints over ingested transactions.

**Out of scope (future phases):**
- Price/m² estimation endpoints.
- Automated fetching/scraping of council portals (ingestion is manual-file-driven for now).
- Frontend.
- Auth (API is public/read-only, no write endpoints exposed over HTTP).

## Data source (Belo Horizonte)

CSV, `;`-delimited, comma as decimal separator, dates as `dd/mm/yyyy`. Columns:

```
Endereco Completo; Bairro; Ano de Construcao (Unidade); Area Terreno Total;
Area Construida Adquirida; Area Adquirida (Unidades Somadas);
Padrao Acabamento (Unidade); Fracao Ideal Adquirida; Tipo Construtivo Preponderante;
Descrição Tipo Ocupacao (Unidade); Valor Declarado; Valor Base Calculo;
Zona Uso ITBI; Data Quitacao
```

Sample row:
```
AVE AUGUSTO DE LIMA 134 - APT 1201 - CENTRO - 30190-001 - BELO HORIZONTE - MG;
CENTRO;1965;1080;47,25;47,25;P3;0,00333;AP;RESIDENCIAL;270000;270000;ZHIP;01/06/2026
```

`Endereco Completo` packs street+number+complement, neighborhood, CEP, city, and UF
into one `" - "`-delimited string. Neighborhood/city/UF are redundant with other
columns or inferable, but street/number/complement and CEP need to be parsed out.

`Valor Declarado` (declared value) is what the buyer reported; `Valor Base Calculo`
(assessed base value) is the council's own valuation and can be higher when
declared value looks lowballed. Both are kept — assessed value is likely the more
reliable market signal for future estimation work.

## Architecture

- **FastAPI** read API — `app/api/routes/transactions.py`.
- **PostgreSQL** storage via **SQLAlchemy 2.0**, migrations via **Alembic**.
- **Ingestion is a CLI step, not an HTTP endpoint**: `python -m app.ingestion.cli
  ingest --city belo_horizonte --file data.csv`. No file-upload/auth surface needed
  for the MVP; re-running ingestion is safe (see dedup below).
- **Adapter pattern per city**: each city has a small module mapping its raw export
  format to the common `Transaction` schema. Adding a new city means adding a new
  adapter, not touching the core model or API. `app/ingestion/base.py` defines the
  adapter protocol; `app/ingestion/belo_horizonte.py` is the first implementation.

## Data model

Single `transactions` table, normalized across cities:

| field | source (BH) | notes |
|---|---|---|
| `id` | — | PK, serial |
| `city` | — | e.g. `"belo_horizonte"` |
| `source_row_hash` | — | SHA-256 of the normalized raw row; **unique constraint** makes re-ingestion idempotent (no duplicate rows on re-run) |
| `raw_address` | Endereco Completo | kept verbatim for audit |
| `street_line` | parsed from Endereco Completo | tokens before neighborhood/CEP: street, number, complement |
| `postal_code` | parsed via regex `\d{5}-\d{3}` from Endereco Completo | |
| `neighborhood` | Bairro | |
| `construction_year` | Ano de Construcao | nullable |
| `land_area` | Area Terreno Total | numeric, comma→dot |
| `built_area_acquired` | Area Construida Adquirida | numeric |
| `acquired_area_total` | Area Adquirida (Unidades Somadas) | numeric |
| `finish_standard` | Padrao Acabamento | e.g. P3/P4/P5 |
| `acquired_fraction` | Fracao Ideal Adquirida | numeric |
| `construction_type` | Tipo Construtivo Preponderante | e.g. AP, CA |
| `occupation_type` | Descrição Tipo Ocupacao | e.g. RESIDENCIAL, COMERCIAL |
| `declared_value` | Valor Declarado | numeric |
| `calc_base_value` | Valor Base Calculo | numeric |
| `zoning` | Zona Uso ITBI | |
| `settlement_date` | Data Quitacao | parsed date |
| `created_at` | — | ingestion timestamp, server default now() |

Address parsing (BH adapter): split `Endereco Completo` on `" - "`; the CEP token
(regex-matched) anchors the split — everything after it is city/UF (discarded,
redundant), the token immediately before it is neighborhood (also redundant with
the `Bairro` column, used as a cross-check), and everything before that is joined
back into `street_line`.

## API endpoints (MVP)

All read-only:

- `GET /transactions` — filters: `city`, `neighborhood`, `min_value`/`max_value`
  (on `declared_value`), `min_area`/`max_area` (on `built_area_acquired`),
  `construction_type`, `occupation_type`, `date_from`/`date_to` (on
  `settlement_date`); `limit`/`offset` pagination; sort by value/date/area.
- `GET /transactions/{id}`
- `GET /cities` — distinct ingested cities
- `GET /neighborhoods?city=` — distinct neighborhoods for a city, for building
  filter UI later

No estimation endpoint in this phase.

## Project layout

```
app/
  main.py
  core/
    config.py            # pydantic-settings: DATABASE_URL, etc.
  db/
    session.py
    base.py
  models/
    transaction.py
  schemas/
    transaction.py        # pydantic request/response schemas
  api/
    routes/
      transactions.py
  ingestion/
    base.py                # Adapter protocol
    belo_horizonte.py       # BH CSV -> Transaction rows
    cli.py                  # `ingest --city X --file Y` (typer/click)
alembic/
  versions/
tests/
  test_adapters/
    test_belo_horizonte.py  # parse sample rows, assert normalized output
  test_api/
    test_transactions.py    # TestClient against a test DB
docker-compose.yml           # postgres service for local dev
pyproject.toml
README.md
```

## Testing

- Adapter unit tests: feed the BH adapter the sample rows from this spec, assert
  parsed fields (especially `street_line`/`postal_code` extraction and
  numeric/date normalization).
- API tests: `TestClient` against a test database (transactional rollback per test
  or a disposable schema), covering filter combinations and pagination.
- Ingestion idempotency test: run the same file twice, assert row count doesn't
  double (via `source_row_hash` uniqueness).

## Repo / commit policy

Public repo. **No commits are made by the assistant** — the user reviews and
commits all changes themselves.
