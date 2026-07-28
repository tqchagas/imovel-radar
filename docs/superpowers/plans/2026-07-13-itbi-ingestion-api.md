# ITBI Ingestion & Query API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI backend that ingests Belo Horizonte's ITBI open-data CSV into PostgreSQL and exposes it through a read-only, filterable, paginated API.

**Architecture:** FastAPI app backed by PostgreSQL via SQLAlchemy 2.0 + Alembic migrations. Ingestion is a Typer CLI command, not an HTTP endpoint. Each city gets its own parser module ("adapter") that maps raw CSV rows into one common `ParsedTransaction` shape; the loader inserts new rows keyed on a content hash so re-running ingestion never creates duplicates.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL (psycopg driver), Pydantic v2 / pydantic-settings, Typer, pytest, httpx (FastAPI TestClient).

## Global Constraints

- **No git commits are made by the implementer at any point, local or remote.** Each task's final step stages the relevant files (`git add`) and stops there — the user reviews and commits themselves. Do not run `git commit`.
- Public repo: no secrets committed. `.env` is gitignored; `.env.example` documents required vars.
- Data source is Belo Horizonte's CSV export: `;`-delimited, comma-decimal, `dd/mm/yyyy` dates (see spec `docs/superpowers/specs/2026-07-13-itbi-ingestion-api-design.md` for full column list and sample rows).
- No price-estimation endpoint in this phase — read/filter/list only.
- `source_row_hash` uniqueness is the sole dedup mechanism; ingestion must be safely re-runnable.

---

### Task 1: Project scaffolding & health check

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/core/config.py`
- Create: `app/db/base.py`
- Create: `app/db/session.py`
- Create: `app/main.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `app.core.config.settings` (has `.database_url: str`), `app.db.base.Base` (SQLAlchemy `DeclarativeBase`), `app.db.session.SessionLocal` and `app.db.session.get_db()` (FastAPI dependency yielding a `Session`), `app.main.app` (the `FastAPI` instance).

- [ ] **Step 1: Create `requirements.txt`**

```
fastapi>=0.110
uvicorn[standard]>=0.29
sqlalchemy>=2.0
psycopg[binary]>=3.1
alembic>=1.13
pydantic-settings>=2.2
typer>=0.12
python-dotenv>=1.0
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

- [ ] **Step 4: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: imovelradar
      POSTGRES_PASSWORD: imovelradar
      POSTGRES_DB: imovelradar
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

- [ ] **Step 5: Create `.env.example`**

```
DATABASE_URL=postgresql+psycopg://imovelradar:imovelradar@localhost:5432/imovelradar
```

- [ ] **Step 6: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
.venv/
venv/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 7: Create `app/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://imovelradar:imovelradar@localhost:5432/imovelradar"
    )


settings = Settings()
```

- [ ] **Step 8: Create `app/db/base.py`**

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 9: Create `app/db/session.py`**

```python
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 10: Create `app/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="ImovelRadar API")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 11: Write the failing test — `tests/test_health.py`**

```python
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 12: Install dependencies and run the test**

Run:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/test_health.py -v
```
Expected: PASS (this is the first test — it should pass immediately since `app/main.py` already defines `/health`; if it fails, check that `pythonpath = ["."]` is present in `pyproject.toml` and you're running `pytest` from the repo root).

- [ ] **Step 13: Stage changes (do not commit — user commits)**

```bash
git init
git add requirements.txt requirements-dev.txt pyproject.toml docker-compose.yml .env.example .gitignore app tests
```

---

### Task 2: Transaction model + Alembic migration

**Files:**
- Create: `app/models/transaction.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_create_transactions.py`
- Test: `tests/test_models/test_transaction.py`

**Interfaces:**
- Consumes: `app.db.base.Base` (Task 1).
- Produces: `app.models.transaction.Transaction` SQLAlchemy model with columns: `id, city, source_row_hash, raw_address, street_line, postal_code, neighborhood, construction_year, land_area, built_area_acquired, acquired_area_total, finish_standard, acquired_fraction, construction_type, occupation_type, declared_value, calc_base_value, zoning, settlement_date, created_at`.

- [ ] **Step 1: Create `app/models/transaction.py`**

```python
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city: Mapped[str] = mapped_column(String(100), index=True)
    source_row_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    raw_address: Mapped[str] = mapped_column(String(500))
    street_line: Mapped[str] = mapped_column(String(300))
    postal_code: Mapped[str | None] = mapped_column(String(9), nullable=True)
    neighborhood: Mapped[str] = mapped_column(String(150), index=True)
    construction_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    land_area: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    built_area_acquired: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    acquired_area_total: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    finish_standard: Mapped[str | None] = mapped_column(String(10), nullable=True)
    acquired_fraction: Mapped[float | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    construction_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    occupation_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    declared_value: Mapped[float] = mapped_column(Numeric(14, 2))
    calc_base_value: Mapped[float] = mapped_column(Numeric(14, 2))
    zoning: Mapped[str | None] = mapped_column(String(20), nullable=True)
    settlement_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 2: Write the failing test — `tests/test_models/test_transaction.py`**

```python
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.transaction import Transaction


def test_transaction_table_created_and_insertable() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Transaction(
                city="belo_horizonte",
                source_row_hash="abc123",
                raw_address="RUA TESTE 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG",
                street_line="RUA TESTE 1",
                postal_code="30000-000",
                neighborhood="CENTRO",
                construction_year=2000,
                land_area=100.0,
                built_area_acquired=80.0,
                acquired_area_total=80.0,
                finish_standard="P3",
                acquired_fraction=1.0,
                construction_type="AP",
                occupation_type="RESIDENCIAL",
                declared_value=200000.0,
                calc_base_value=200000.0,
                zoning="ZA",
                settlement_date=date(2026, 6, 1),
            )
        )
        session.commit()

        result = session.query(Transaction).one()
        assert result.city == "belo_horizonte"
        assert result.neighborhood == "CENTRO"
```

This test needs no real Postgres — it runs against an in-memory SQLite DB, since we only need to check the model/mapping itself, not the migration.

- [ ] **Step 3: Run test to verify it fails first, then passes**

Run: `pytest tests/test_models/test_transaction.py -v`
Expected before Step 1's file exists: FAIL with `ModuleNotFoundError: No module named 'app.models'`. After Step 1: PASS.

- [ ] **Step 4: Create `alembic.ini`**

```ini
[alembic]
script_location = alembic
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 5: Create `alembic/env.py`**

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base
from app.models.transaction import Transaction  # noqa: F401  (registers the model)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 6: Create `alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 7: Create `alembic/versions/0001_create_transactions.py`**

```python
"""create transactions table

Revision ID: 0001
Revises:
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_address", sa.String(length=500), nullable=False),
        sa.Column("street_line", sa.String(length=300), nullable=False),
        sa.Column("postal_code", sa.String(length=9), nullable=True),
        sa.Column("neighborhood", sa.String(length=150), nullable=False),
        sa.Column("construction_year", sa.Integer(), nullable=True),
        sa.Column("land_area", sa.Numeric(14, 2), nullable=True),
        sa.Column("built_area_acquired", sa.Numeric(14, 2), nullable=True),
        sa.Column("acquired_area_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("finish_standard", sa.String(length=10), nullable=True),
        sa.Column("acquired_fraction", sa.Numeric(10, 6), nullable=True),
        sa.Column("construction_type", sa.String(length=10), nullable=True),
        sa.Column("occupation_type", sa.String(length=50), nullable=True),
        sa.Column("declared_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("calc_base_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("zoning", sa.String(length=20), nullable=True),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source_row_hash", name="uq_transactions_source_row_hash"),
    )
    op.create_index("ix_transactions_city", "transactions", ["city"])
    op.create_index("ix_transactions_neighborhood", "transactions", ["neighborhood"])
    op.create_index(
        "ix_transactions_settlement_date", "transactions", ["settlement_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_settlement_date", table_name="transactions")
    op.drop_index("ix_transactions_neighborhood", table_name="transactions")
    op.drop_index("ix_transactions_city", table_name="transactions")
    op.drop_table("transactions")
```

- [ ] **Step 8: Manually verify the migration against real Postgres**

Run:
```bash
docker compose up -d postgres
cp .env.example .env
alembic upgrade head
```
Expected: no errors, and `psql postgresql://imovelradar:imovelradar@localhost:5432/imovelradar -c '\d transactions'` shows the table with all 20 columns.

- [ ] **Step 9: Stage changes (do not commit — user commits)**

```bash
git add app/models alembic alembic.ini tests/test_models
```

---

### Task 3: Belo Horizonte ingestion adapter

**Files:**
- Create: `app/ingestion/base.py`
- Create: `app/ingestion/belo_horizonte.py`
- Test: `tests/test_adapters/test_belo_horizonte.py`
- Test fixture: `tests/fixtures/belo_horizonte_sample.csv`

**Interfaces:**
- Consumes: nothing new (pure parsing, no DB).
- Produces: `app.ingestion.base.ParsedTransaction` (dataclass with fields matching `Transaction` minus `id`/`created_at`), `app.ingestion.belo_horizonte.parse_row(row: dict[str, str]) -> ParsedTransaction`, `app.ingestion.belo_horizonte.parse_file(path: str) -> Iterator[ParsedTransaction]`, `app.ingestion.belo_horizonte.CITY = "belo_horizonte"`.

- [ ] **Step 1: Create `app/ingestion/base.py`**

```python
from dataclasses import dataclass
from datetime import date


@dataclass
class ParsedTransaction:
    city: str
    source_row_hash: str
    raw_address: str
    street_line: str
    postal_code: str | None
    neighborhood: str
    construction_year: int | None
    land_area: float | None
    built_area_acquired: float | None
    acquired_area_total: float | None
    finish_standard: str | None
    acquired_fraction: float | None
    construction_type: str | None
    occupation_type: str | None
    declared_value: float
    calc_base_value: float
    zoning: str | None
    settlement_date: date
```

- [ ] **Step 2: Create the test fixture — `tests/fixtures/belo_horizonte_sample.csv`**

```
Endereco Completo;Bairro;Ano de Construcao (Unidade);Area Terreno Total;Area Construida Adquirida;Area Adquirida (Unidades Somadas);Padrao Acabamento (Unidade);Fracao Ideal Adquirida;Tipo Construtivo Preponderante;Descrição Tipo Ocupacao (Unidade);Valor Declarado;Valor Base Calculo;Zona Uso ITBI;Data Quitacao
AVE AUGUSTO DE LIMA 134 - APT 1201 - CENTRO - 30190-001 - BELO HORIZONTE - MG;CENTRO;1965;1080;47,25;47,25;P3;0,00333;AP;RESIDENCIAL;270000;270000;ZHIP;01/06/2026
AVE JOSE CANDIDO DA SILVEIRA 135 - APT 202 - CIDADE NOVA - 31170-193 - BELO HORIZONTE - MG;CIDADE NOVA;1976;360;89,5;89,5;P3;0,120946;AP;RESIDENCIAL;290000;353615,16;ZA;01/06/2026
```

- [ ] **Step 3: Write the failing test — `tests/test_adapters/test_belo_horizonte.py`**

```python
from datetime import date

from app.ingestion.belo_horizonte import CITY, parse_file, parse_row

SAMPLE_ROW = {
    "Endereco Completo": (
        "AVE AUGUSTO DE LIMA 134 - APT 1201 - CENTRO - 30190-001 - "
        "BELO HORIZONTE - MG"
    ),
    "Bairro": "CENTRO",
    "Ano de Construcao (Unidade)": "1965",
    "Area Terreno Total": "1080",
    "Area Construida Adquirida": "47,25",
    "Area Adquirida (Unidades Somadas)": "47,25",
    "Padrao Acabamento (Unidade)": "P3",
    "Fracao Ideal Adquirida": "0,00333",
    "Tipo Construtivo Preponderante": "AP",
    "Descrição Tipo Ocupacao (Unidade)": "RESIDENCIAL",
    "Valor Declarado": "270000",
    "Valor Base Calculo": "270000",
    "Zona Uso ITBI": "ZHIP",
    "Data Quitacao": "01/06/2026",
}


def test_parse_row_extracts_street_line_and_postal_code() -> None:
    parsed = parse_row(SAMPLE_ROW)

    assert parsed.city == CITY
    assert parsed.street_line == "AVE AUGUSTO DE LIMA 134 - APT 1201"
    assert parsed.postal_code == "30190-001"
    assert parsed.neighborhood == "CENTRO"


def test_parse_row_normalizes_numbers_and_dates() -> None:
    parsed = parse_row(SAMPLE_ROW)

    assert parsed.construction_year == 1965
    assert parsed.land_area == 1080.0
    assert parsed.built_area_acquired == 47.25
    assert parsed.acquired_fraction == 0.00333
    assert parsed.declared_value == 270000.0
    assert parsed.settlement_date == date(2026, 6, 1)


def test_parse_row_is_deterministic_for_dedup_hash() -> None:
    first = parse_row(SAMPLE_ROW)
    second = parse_row(SAMPLE_ROW)
    assert first.source_row_hash == second.source_row_hash


def test_parse_file_reads_all_rows() -> None:
    rows = list(parse_file("tests/fixtures/belo_horizonte_sample.csv"))
    assert len(rows) == 2
    assert rows[0].neighborhood == "CENTRO"
    assert rows[1].neighborhood == "CIDADE NOVA"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_adapters/test_belo_horizonte.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion'`.

- [ ] **Step 5: Create `app/ingestion/belo_horizonte.py`**

```python
import csv
import hashlib
import re
from collections.abc import Iterator
from datetime import date, datetime

from app.ingestion.base import ParsedTransaction

CITY = "belo_horizonte"
POSTAL_CODE_RE = re.compile(r"^\d{5}-\d{3}$")


def _parse_decimal(raw: str) -> float | None:
    raw = raw.strip()
    if not raw:
        return None
    return float(raw.replace(",", "."))


def _parse_int(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    return int(raw)


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%d/%m/%Y").date()


def _split_address(raw_address: str) -> tuple[str, str | None]:
    tokens = [t.strip() for t in raw_address.split(" - ")]
    for i, token in enumerate(tokens):
        if POSTAL_CODE_RE.match(token):
            street_line = " - ".join(tokens[: i - 1]) if i >= 2 else raw_address
            return street_line, token
    return raw_address, None


def _row_hash(row: dict[str, str]) -> str:
    canonical = ";".join(row[key] for key in sorted(row))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_row(row: dict[str, str]) -> ParsedTransaction:
    raw_address = row["Endereco Completo"].strip()
    street_line, postal_code = _split_address(raw_address)
    return ParsedTransaction(
        city=CITY,
        source_row_hash=_row_hash(row),
        raw_address=raw_address,
        street_line=street_line,
        postal_code=postal_code,
        neighborhood=row["Bairro"].strip(),
        construction_year=_parse_int(row["Ano de Construcao (Unidade)"]),
        land_area=_parse_decimal(row["Area Terreno Total"]),
        built_area_acquired=_parse_decimal(row["Area Construida Adquirida"]),
        acquired_area_total=_parse_decimal(row["Area Adquirida (Unidades Somadas)"]),
        finish_standard=row["Padrao Acabamento (Unidade)"].strip() or None,
        acquired_fraction=_parse_decimal(row["Fracao Ideal Adquirida"]),
        construction_type=row["Tipo Construtivo Preponderante"].strip() or None,
        occupation_type=row["Descrição Tipo Ocupacao (Unidade)"].strip() or None,
        declared_value=_parse_decimal(row["Valor Declarado"]) or 0.0,
        calc_base_value=_parse_decimal(row["Valor Base Calculo"]) or 0.0,
        zoning=row["Zona Uso ITBI"].strip() or None,
        settlement_date=_parse_date(row["Data Quitacao"]),
    )


def parse_file(path: str) -> Iterator[ParsedTransaction]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            yield parse_row(row)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_adapters/test_belo_horizonte.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Stage changes (do not commit — user commits)**

```bash
git add app/ingestion/base.py app/ingestion/belo_horizonte.py tests/test_adapters tests/fixtures
```

---

### Task 4: Ingestion loader + CLI

**Files:**
- Create: `app/ingestion/loader.py`
- Create: `app/ingestion/cli.py`
- Test: `tests/conftest.py`
- Test: `tests/test_ingestion/test_loader.py`

**Interfaces:**
- Consumes: `app.ingestion.base.ParsedTransaction` (Task 3), `app.models.transaction.Transaction` (Task 2), `app.db.session.SessionLocal` (Task 1).
- Produces: `app.ingestion.loader.load_transactions(db: Session, records: Iterable[ParsedTransaction]) -> int` (returns count of newly inserted rows), CLI command `python -m app.ingestion.cli ingest --city <city> --file <path>`.

- [ ] **Step 1: Create `tests/conftest.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.transaction import Transaction  # noqa: F401  (registers the table)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
```

- [ ] **Step 2: Write the failing test — `tests/test_ingestion/test_loader.py`**

```python
from datetime import date

from app.ingestion.base import ParsedTransaction
from app.ingestion.loader import load_transactions
from app.models.transaction import Transaction


def _record(hash_suffix: str) -> ParsedTransaction:
    return ParsedTransaction(
        city="belo_horizonte",
        source_row_hash=f"hash-{hash_suffix}",
        raw_address="RUA TESTE 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG",
        street_line="RUA TESTE 1",
        postal_code="30000-000",
        neighborhood="CENTRO",
        construction_year=2000,
        land_area=100.0,
        built_area_acquired=80.0,
        acquired_area_total=80.0,
        finish_standard="P3",
        acquired_fraction=1.0,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=200000.0,
        calc_base_value=200000.0,
        zoning="ZA",
        settlement_date=date(2026, 6, 1),
    )


def test_load_transactions_inserts_new_records(db_session) -> None:
    inserted = load_transactions(db_session, [_record("a"), _record("b")])

    assert inserted == 2
    assert db_session.query(Transaction).count() == 2


def test_load_transactions_is_idempotent_on_rerun(db_session) -> None:
    records = [_record("a"), _record("b")]

    first_run = load_transactions(db_session, records)
    second_run = load_transactions(db_session, records)

    assert first_run == 2
    assert second_run == 0
    assert db_session.query(Transaction).count() == 2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_ingestion/test_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.loader'`.

- [ ] **Step 4: Create `app/ingestion/loader.py`**

```python
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.base import ParsedTransaction
from app.models.transaction import Transaction


def load_transactions(db: Session, records: Iterable[ParsedTransaction]) -> int:
    records = list(records)
    hashes = [r.source_row_hash for r in records]

    existing = set(
        db.scalars(
            select(Transaction.source_row_hash).where(
                Transaction.source_row_hash.in_(hashes)
            )
        )
    )

    new_rows = [
        Transaction(**r.__dict__)
        for r in records
        if r.source_row_hash not in existing
    ]
    db.add_all(new_rows)
    db.commit()
    return len(new_rows)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_ingestion/test_loader.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Create `app/ingestion/cli.py`**

```python
import typer

from app.db.session import SessionLocal
from app.ingestion.belo_horizonte import CITY as BELO_HORIZONTE_CITY
from app.ingestion.belo_horizonte import parse_file as parse_belo_horizonte
from app.ingestion.loader import load_transactions

app = typer.Typer()

ADAPTERS = {
    BELO_HORIZONTE_CITY: parse_belo_horizonte,
}


@app.command()
def ingest(city: str, file: str) -> None:
    if city not in ADAPTERS:
        raise typer.BadParameter(f"Unknown city '{city}'. Available: {list(ADAPTERS)}")

    records = ADAPTERS[city](file)
    db = SessionLocal()
    try:
        inserted = load_transactions(db, records)
        typer.echo(f"Inserted {inserted} new transactions for {city}")
    finally:
        db.close()


if __name__ == "__main__":
    app()
```

- [ ] **Step 7: Manually verify the CLI against real Postgres**

Run (with `docker compose up -d postgres` and `alembic upgrade head` already done from Task 2):
```bash
python -m app.ingestion.cli ingest --city belo_horizonte --file tests/fixtures/belo_horizonte_sample.csv
python -m app.ingestion.cli ingest --city belo_horizonte --file tests/fixtures/belo_horizonte_sample.csv
```
Expected: first run prints `Inserted 2 new transactions for belo_horizonte`; second run (same file) prints `Inserted 0 new transactions for belo_horizonte`, confirming dedup works end-to-end.

- [ ] **Step 8: Stage changes (do not commit — user commits)**

```bash
git add app/ingestion/loader.py app/ingestion/cli.py tests/conftest.py tests/test_ingestion
```

---

### Task 5: Transaction schemas + read API endpoints

**Files:**
- Create: `app/schemas/transaction.py`
- Create: `app/api/routes/transactions.py`
- Modify: `app/main.py`
- Test: `tests/test_api/test_transactions.py`

**Interfaces:**
- Consumes: `app.models.transaction.Transaction` (Task 2), `app.db.session.get_db` (Task 1).
- Produces: `app.schemas.transaction.TransactionOut`, `app.schemas.transaction.TransactionList` (`{total: int, items: list[TransactionOut]}`), router mounted on `app.main.app` exposing `GET /transactions`, `GET /transactions/{id}`, `GET /cities`, `GET /neighborhoods`.

- [ ] **Step 1: Create `app/schemas/transaction.py`**

```python
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city: str
    raw_address: str
    street_line: str
    postal_code: str | None
    neighborhood: str
    construction_year: int | None
    land_area: float | None
    built_area_acquired: float | None
    acquired_area_total: float | None
    finish_standard: str | None
    acquired_fraction: float | None
    construction_type: str | None
    occupation_type: str | None
    declared_value: float
    calc_base_value: float
    zoning: str | None
    settlement_date: date
    created_at: datetime


class TransactionList(BaseModel):
    total: int
    items: list[TransactionOut]
```

- [ ] **Step 2: Write the failing test — `tests/test_api/test_transactions.py`**

```python
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.transaction import Transaction

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(bind=engine)


def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Transaction(
                city="belo_horizonte",
                source_row_hash="hash-1",
                raw_address="RUA A 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG",
                street_line="RUA A 1",
                postal_code="30000-000",
                neighborhood="CENTRO",
                construction_year=2000,
                land_area=100.0,
                built_area_acquired=60.0,
                acquired_area_total=60.0,
                finish_standard="P3",
                acquired_fraction=1.0,
                construction_type="AP",
                occupation_type="RESIDENCIAL",
                declared_value=300000.0,
                calc_base_value=300000.0,
                zoning="ZA",
                settlement_date=date(2026, 5, 1),
            )
        )
        session.add(
            Transaction(
                city="belo_horizonte",
                source_row_hash="hash-2",
                raw_address="RUA B 2 - LOURDES - 30100-000 - BELO HORIZONTE - MG",
                street_line="RUA B 2",
                postal_code="30100-000",
                neighborhood="LOURDES",
                construction_year=2010,
                land_area=200.0,
                built_area_acquired=120.0,
                acquired_area_total=120.0,
                finish_standard="P4",
                acquired_fraction=1.0,
                construction_type="AP",
                occupation_type="RESIDENCIAL",
                declared_value=900000.0,
                calc_base_value=900000.0,
                zoning="ZCBH",
                settlement_date=date(2026, 6, 1),
            )
        )
        session.commit()
    yield
    Base.metadata.drop_all(engine)


client = TestClient(app)


def test_list_transactions_returns_all_by_default() -> None:
    response = client.get("/transactions")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_transactions_filters_by_neighborhood() -> None:
    response = client.get("/transactions", params={"neighborhood": "LOURDES"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["neighborhood"] == "LOURDES"


def test_list_transactions_filters_by_value_range() -> None:
    response = client.get(
        "/transactions", params={"min_value": 500000, "max_value": 1000000}
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["declared_value"] == 900000.0


def test_get_transaction_by_id() -> None:
    listing = client.get("/transactions").json()
    first_id = listing["items"][0]["id"]

    response = client.get(f"/transactions/{first_id}")
    assert response.status_code == 200
    assert response.json()["id"] == first_id


def test_get_transaction_404_for_missing_id() -> None:
    response = client.get("/transactions/999999")
    assert response.status_code == 404


def test_list_cities() -> None:
    response = client.get("/cities")
    assert response.status_code == 200
    assert response.json() == ["belo_horizonte"]


def test_list_neighborhoods_for_city() -> None:
    response = client.get("/neighborhoods", params={"city": "belo_horizonte"})
    assert response.status_code == 200
    assert sorted(response.json()) == ["CENTRO", "LOURDES"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_api/test_transactions.py -v`
Expected: FAIL with 404s (routes don't exist yet — `app/main.py` only has `/health`).

- [ ] **Step 4: Create `app/api/routes/transactions.py`**

```python
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionList, TransactionOut

router = APIRouter()


@router.get("/transactions", response_model=TransactionList)
def list_transactions(
    city: str | None = None,
    neighborhood: str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    construction_type: str | None = None,
    occupation_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(50, le=200, gt=0),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> TransactionList:
    stmt = select(Transaction)
    if city:
        stmt = stmt.where(Transaction.city == city)
    if neighborhood:
        stmt = stmt.where(Transaction.neighborhood == neighborhood)
    if min_value is not None:
        stmt = stmt.where(Transaction.declared_value >= min_value)
    if max_value is not None:
        stmt = stmt.where(Transaction.declared_value <= max_value)
    if min_area is not None:
        stmt = stmt.where(Transaction.built_area_acquired >= min_area)
    if max_area is not None:
        stmt = stmt.where(Transaction.built_area_acquired <= max_area)
    if construction_type:
        stmt = stmt.where(Transaction.construction_type == construction_type)
    if occupation_type:
        stmt = stmt.where(Transaction.occupation_type == occupation_type)
    if date_from is not None:
        stmt = stmt.where(Transaction.settlement_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.settlement_date <= date_to)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(Transaction.settlement_date.desc()).limit(limit).offset(offset)
    ).all()
    return TransactionList(
        total=total, items=[TransactionOut.model_validate(i) for i in items]
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)) -> Transaction:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@router.get("/cities", response_model=list[str])
def list_cities(db: Session = Depends(get_db)) -> list[str]:
    return list(db.scalars(select(Transaction.city).distinct()))


@router.get("/neighborhoods", response_model=list[str])
def list_neighborhoods(city: str, db: Session = Depends(get_db)) -> list[str]:
    stmt = select(Transaction.neighborhood).distinct().where(Transaction.city == city)
    return list(db.scalars(stmt))
```

- [ ] **Step 5: Modify `app/main.py`**

```python
from fastapi import FastAPI

from app.api.routes.transactions import router as transactions_router

app = FastAPI(title="ImovelRadar API")
app.include_router(transactions_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_api/test_transactions.py -v`
Expected: PASS (7 tests).

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every task pass.

- [ ] **Step 8: Stage changes (do not commit — user commits)**

```bash
git add app/schemas app/api app/main.py tests/test_api
```

---

### Task 6: README & end-to-end manual verification

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: nothing new for other tasks to consume (final task).

- [ ] **Step 1: Create `README.md`**

```markdown
# ImovelRadar

Public dataset + API of Brazilian real-estate transactions, sourced from ITBI
(property transfer tax) open data published by city councils. Settled ITBI
implies a real transaction at a real declared value — the goal is to use this
as a price signal. Coverage is limited to cities that publish this data openly.

Currently covered: **Belo Horizonte (MG)**.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d postgres
alembic upgrade head
```

## Running the API

```bash
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`.

## Ingesting data

Download Belo Horizonte's ITBI CSV export and run:

```bash
python -m app.ingestion.cli ingest --city belo_horizonte --file /path/to/file.csv
```

Re-running ingestion on the same file is safe — rows are deduplicated by content
hash.

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
```

- [ ] **Step 2: Run the full test suite one last time**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 3: Manual end-to-end smoke test**

Run:
```bash
uvicorn app.main:app --reload &
sleep 2
curl http://localhost:8000/health
curl "http://localhost:8000/transactions?neighborhood=CENTRO"
curl http://localhost:8000/cities
kill %1
```
Expected: `/health` returns `{"status":"ok"}`; `/transactions` returns whatever was ingested in Task 4's manual verification step (or an empty list/`total: 0` if that DB was reset); `/cities` returns `["belo_horizonte"]` if data was ingested.

- [ ] **Step 4: Stage changes (do not commit — user commits)**

```bash
git add README.md
```

All tasks are now staged but uncommitted. Review with `git status`/`git diff --cached` and commit at your own pace.
