from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex
from app.models.transaction import Transaction
from app.services import deflator as servico_deflator

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


def _transaction(
    suffix: str,
    *,
    neighborhood: str,
    street: str,
    day: date,
    value: float,
    area: float,
) -> Transaction:
    return Transaction(
        city="belo_horizonte",
        source_row_hash=f"hash-{suffix}",
        raw_address=f"{street} 1 - {neighborhood}",
        street=street,
        street_number="1",
        complement=f"AP {suffix}",
        postal_code="30000-000",
        neighborhood=neighborhood,
        construction_year=2000,
        land_area=100.0,
        built_area_acquired=area,
        acquired_area_total=area,
        finish_standard="P3",
        acquired_fraction=1.0,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=value,
        calc_base_value=value,
        zoning="ZA",
        settlement_date=day,
    )


@pytest.fixture(autouse=True)
def _reset_db():
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                _transaction(
                    "1",
                    neighborhood="SAVASSI",
                    street="RUA A",
                    day=date(2025, 6, 1),
                    value=1_000_000,
                    area=100,
                ),
                _transaction(
                    "2",
                    neighborhood="SAVASSI",
                    street="RUA A",
                    day=date(2025, 5, 1),
                    value=1_000_000,
                    area=100,
                ),
                _transaction(
                    "3",
                    neighborhood="SAVASSI",
                    street="RUA A",
                    day=date(2024, 6, 1),
                    value=800_000,
                    area=100,
                ),
                _transaction(
                    "4",
                    neighborhood="LOURDES",
                    street="RUA B",
                    day=date(2025, 4, 1),
                    value=1_400_000,
                    area=100,
                ),
            ]
        )
        session.commit()
    yield
    Base.metadata.drop_all(engine)


client = TestClient(app)


def _semear_ipca() -> None:
    """Mai/2025 sobe 0%, jun/2025 sobe 10%: fator 1,10 para trazer mai/2025
    até a referência de jun/2025, e fator 1,0 para jun/2025 contra si mesma."""
    servico_deflator.invalidar_cache()
    with Session(engine) as session:
        session.add_all(
            [
                MonetaryIndex(series=SERIE_IPCA, competencia=date(2025, 5, 1), variacao_pct=0.0),
                MonetaryIndex(series=SERIE_IPCA, competencia=date(2025, 6, 1), variacao_pct=10.0),
            ]
        )
        session.commit()


def test_overview_counts_rows_neighborhoods_and_years() -> None:
    body = client.get("/stats/overview", params={"city": "belo_horizonte"}).json()
    assert body["transaction_count"] == 4
    assert body["neighborhood_count"] == 2
    assert body["year_from"] == 2024
    assert body["year_to"] == 2025
    assert body["last_settlement_date"] == "2025-06-01"


def test_neighborhood_ranking_uses_latest_settlement_as_reference() -> None:
    body = client.get(
        "/stats/neighborhoods",
        params={"city": "belo_horizonte", "months": 12, "min_transactions": 1},
    ).json()

    assert body["reference_date"] == "2025-06-01"
    assert [i["neighborhood"] for i in body["items"]] == ["LOURDES", "SAVASSI"]
    savassi = body["items"][1]
    assert savassi["median_price_per_m2"] == 10_000
    assert savassi["transaction_count"] == 2


def test_neighborhood_ranking_is_empty_without_data() -> None:
    body = client.get("/stats/neighborhoods", params={"city": "outra_cidade"}).json()
    assert body["items"] == []


def test_neighborhood_detail_returns_breakdowns() -> None:
    body = client.get(
        "/stats/neighborhoods/SAVASSI", params={"city": "belo_horizonte"}
    ).json()

    assert body["transaction_count"] == 2
    assert body["median_price_per_m2"] == 10_000
    assert body["delta_pct"] == 25.0
    assert body["residential_share_pct"] == 100.0
    assert body["by_construction_type"][0]["construction_type"] == "AP"


def test_neighborhood_detail_404_for_unknown_neighborhood() -> None:
    response = client.get(
        "/stats/neighborhoods/INEXISTENTE", params={"city": "belo_horizonte"}
    )
    assert response.status_code == 404


def test_street_detail_returns_market_metrics_and_addresses() -> None:
    response = client.get(
        "/stats/streets/RUA A",
        params={"city": "belo_horizonte"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["street"] == "RUA A"
    assert body["transaction_count"] == 2
    assert body["property_count"] == 1
    assert body["median_ticket"] == 1_000_000
    assert body["top_addresses"][0]["street_number"] == "1"


def test_street_detail_404_for_unknown_street() -> None:
    response = client.get(
        "/stats/streets/INEXISTENTE",
        params={"city": "belo_horizonte"},
    )

    assert response.status_code == 404


def test_street_detail_brings_corrected_median_beside_nominal() -> None:
    # RUA A no ano corrente tem duas vendas a R$ 10.000/m²: uma de jun/2025
    # (fator 1,0, é a própria referência) e outra de mai/2025 (fator 1,10).
    # A mediana nominal não muda; a corrigida passa a ser 10.500.
    _semear_ipca()
    response = client.get(
        "/stats/streets/RUA A",
        params={"city": "belo_horizonte"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["median_price_per_m2"] == 10_000
    assert body["median_price_per_m2_corrected"] == pytest.approx(10_500)
    assert body["correction_reference"] == "2025-06-01"


def test_street_detail_corrected_is_null_without_series() -> None:
    response = client.get(
        "/stats/streets/RUA A",
        params={"city": "belo_horizonte"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["median_price_per_m2"] == 10_000
    assert body["median_price_per_m2_corrected"] is None
    assert body["correction_reference"] is None


def test_neighborhood_detail_brings_corrected_median_beside_nominal() -> None:
    # Mesmas duas vendas de SAVASSI que compõem a mediana nominal de 10.000.
    _semear_ipca()
    body = client.get(
        "/stats/neighborhoods/SAVASSI", params={"city": "belo_horizonte"}
    ).json()

    assert body["median_price_per_m2"] == 10_000
    assert body["median_price_per_m2_corrected"] == pytest.approx(10_500)
    assert body["correction_reference"] == "2025-06-01"


def test_neighborhood_detail_corrected_is_null_without_series() -> None:
    body = client.get(
        "/stats/neighborhoods/SAVASSI", params={"city": "belo_horizonte"}
    ).json()

    assert body["median_price_per_m2"] == 10_000
    assert body["median_price_per_m2_corrected"] is None
    assert body["correction_reference"] is None
