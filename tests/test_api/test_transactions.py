from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.transaction import Transaction

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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
    # Re-bind for this module: other API test modules also override get_db.
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            Transaction(
                city="belo_horizonte",
                source_row_hash="hash-1",
                raw_address="RUA A 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG",
                street="RUA A",
                street_number="1",
                complement=None,
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
                street="RUA B",
                street_number="2",
                complement=None,
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


def test_list_transactions_sorts_by_price_per_m2() -> None:
    # 900k over 120 m² beats 300k over 60 m², the other way round by value.
    highest = client.get("/transactions", params={"sort": "m2_desc"}).json()
    assert highest["items"][0]["declared_value"] == 900000.0

    lowest = client.get("/transactions", params={"sort": "m2_asc"}).json()
    assert lowest["items"][0]["declared_value"] == 300000.0


def test_list_transactions_rejects_unknown_sort() -> None:
    response = client.get("/transactions", params={"sort": "bogus"})
    assert response.status_code == 400
    assert "bogus" in response.json()["detail"]


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


def test_upload_is_not_published_in_the_public_openapi_schema() -> None:
    assert "/upload" not in app.openapi()["paths"]


SAMPLE_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "belo_horizonte_sample.csv"


def test_upload_itbi_file_inserts_and_is_idempotent() -> None:
    with SAMPLE_CSV.open("rb") as f:
        response = client.post(
            "/upload",
            data={"city": "belo_horizonte"},
            files={"file": ("belo_horizonte_sample.csv", f, "text/csv")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["city"] == "belo_horizonte"
    assert body["total_rows"] == 2
    assert body["inserted"] == 2

    listing = client.get("/transactions").json()
    assert listing["total"] == 4

    with SAMPLE_CSV.open("rb") as f:
        response = client.post(
            "/upload",
            data={"city": "belo_horizonte"},
            files={"file": ("belo_horizonte_sample.csv", f, "text/csv")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["inserted"] == 0
    assert body["total_rows"] == 2

    listing = client.get("/transactions").json()
    assert listing["total"] == 4


def test_upload_itbi_file_rejects_unknown_city() -> None:
    with SAMPLE_CSV.open("rb") as f:
        response = client.post(
            "/upload",
            data={"city": "unknown_city"},
            files={"file": ("belo_horizonte_sample.csv", f, "text/csv")},
        )
    assert response.status_code == 400
    assert "unknown_city" in response.json()["detail"]


def test_bairros_respondem_ao_nome_da_cidade_como_se_escreve() -> None:
    """A cidade é gravada normalizada e quem chama manda o nome por extenso.

    Sem converter, a lista voltava vazia e todo seletor de bairro da interface
    nascia sem opção nenhuma.
    """
    com_espaco = client.get("/neighborhoods", params={"city": "Belo Horizonte"})
    com_chave = client.get("/neighborhoods", params={"city": "belo_horizonte"})
    assert com_espaco.status_code == 200
    assert com_espaco.json() == com_chave.json()
    assert com_espaco.json()
