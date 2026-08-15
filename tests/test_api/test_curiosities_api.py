from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.curiosities import _CACHE, _split_movers, warm_default_curiosities
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


def _transaction(
    suffix: str,
    *,
    street: str = "RUA A",
    number: str = "100",
    complement: str = "AP 101",
    neighborhood: str = "SAVASSI",
    day: date,
    value: float,
    area: float = 100.0,
    fraction: float = 1.0,
) -> Transaction:
    return Transaction(
        city="belo_horizonte",
        source_row_hash=f"hash-{suffix}",
        raw_address=f"{street} {number} - {neighborhood}",
        street=street,
        street_number=number,
        complement=complement,
        postal_code="30000-000",
        neighborhood=neighborhood,
        construction_year=2000,
        land_area=100.0,
        built_area_acquired=area,
        acquired_area_total=area,
        finish_standard="P3",
        acquired_fraction=fraction,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=value,
        calc_base_value=value,
        zoning="ZA",
        settlement_date=day,
    )


def _rows() -> list[Transaction]:
    """Fresh instances per test: ORM objects cannot be reused across sessions."""
    return [
        # One unit sold three times over fifteen years: top unit + appreciation.
        _transaction("1", complement="AP 101", day=date(2010, 1, 10), value=200_000),
        _transaction("2", complement="apto 101", day=date(2018, 1, 10), value=500_000),
        _transaction("3", complement="AP 101", day=date(2025, 1, 10), value=900_000),
        # Same building, other units: makes RUA A 100 the busiest address.
        _transaction("4", complement="AP 202", day=date(2024, 3, 1), value=700_000),
        _transaction("5", complement="AP 303", day=date(2025, 2, 1), value=750_000),
        # A quick resale in another building.
        _transaction(
            "6", street="RUA B", number="200", complement="AP 1", day=date(2025, 1, 1),
            value=400_000,
        ),
        _transaction(
            "7", street="RUA B", number="200", complement="AP 1", day=date(2025, 3, 2),
            value=520_000,
        ),
        # The priciest row on record, in a second neighborhood.
        _transaction(
            "8", street="RUA C", number="300", complement="CO 1",
            neighborhood="LOURDES", day=date(2025, 4, 1), value=5_000_000, area=200,
        ),
    ]


ROW_COUNT = 8


@pytest.fixture(autouse=True)
def _reset_db():
    app.dependency_overrides[get_db] = _override_get_db
    _CACHE.clear()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(_rows())
        session.commit()
    yield
    Base.metadata.drop_all(engine)
    _CACHE.clear()


client = TestClient(app)


def _board(**params):
    return client.get(
        "/stats/curiosities", params={"city": "belo_horizonte", **params}
    ).json()


def test_reports_reference_date_and_total() -> None:
    body = _board()
    assert body["reference_date"] == "2025-04-01"
    assert body["transaction_count"] == ROW_COUNT


def test_busiest_building_leads_the_ranking() -> None:
    top = _board()["top_buildings"][0]
    assert (top["street"], top["street_number"]) == ("RUA A", "100")
    assert top["transaction_count"] == 5
    assert top["unit_count"] == 3


def test_top_unit_merges_complement_spellings() -> None:
    top = _board()["top_units"][0]
    assert top["transaction_count"] == 3
    assert top["unit"]["complement"] == "AP 101"
    assert top["first_settlement_date"] == "2010-01-10"


def test_appreciation_spans_first_and_last_full_sale() -> None:
    top = _board()["top_appreciation"][0]
    assert top["from_value"] == 200_000
    assert top["to_value"] == 900_000
    assert top["total_pct"] == pytest.approx(350.0)
    assert top["annualized_pct"] > 0


def test_fastest_flip_is_the_two_month_resale() -> None:
    top = _board()["fastest_flips"][0]
    assert top["unit"]["street"] == "RUA B"
    assert top["days"] == 60
    assert top["delta_pct"] == pytest.approx(30.0)


def test_records_expose_the_priciest_rows() -> None:
    body = _board()
    assert body["priciest_sales"][0]["declared_value"] == 5_000_000
    assert body["priciest_per_m2"][0]["price_per_m2"] == 25_000


def test_by_month_is_chronological() -> None:
    months = _board()["by_month"]
    assert months[0] == {"year": 2010, "month": 1, "transaction_count": 1}
    # 2010-01, 2018-01, 2024-03, 2025-01 (two rows), 2025-02, 2025-03, 2025-04
    assert [m["transaction_count"] for m in months] == [1, 1, 1, 2, 1, 1, 1]
    assert sum(m["transaction_count"] for m in months) == ROW_COUNT


def test_empty_city_returns_an_empty_board() -> None:
    body = client.get("/stats/curiosities", params={"city": "outra_cidade"}).json()
    assert body["reference_date"] is None
    assert body["transaction_count"] == 0
    assert body["top_buildings"] == []


def test_insights_endpoint_returns_only_evidence_backed_pages() -> None:
    response = client.get(
        "/stats/curiosities/insights", params={"city": "belo_horizonte"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["city"] == "belo_horizonte"
    assert body["transaction_count"] == ROW_COUNT
    slugs = {item["slug"] for item in body["items"]}
    assert {"maiores-vendas", "ruas-mais-movimentadas"} <= slugs
    assert all(item["url"].startswith("/curiosidades/belo-horizonte/") for item in body["items"])


def test_curiosities_can_be_filtered_by_construction_type() -> None:
    response = client.get(
        "/stats/curiosities",
        params={"city": "belo_horizonte", "construction_type": "CA"},
    )

    assert response.status_code == 200
    assert response.json()["transaction_count"] == 0


def test_movers_never_put_positive_neighborhoods_in_fallers() -> None:
    ranked = [
        SimpleNamespace(delta_pct=12),
        SimpleNamespace(delta_pct=3),
        SimpleNamespace(delta_pct=-2),
        SimpleNamespace(delta_pct=-15),
    ]

    risers, fallers = _split_movers(ranked)

    assert [item.delta_pct for item in risers] == [12, 3]
    assert [item.delta_pct for item in fallers] == [-15, -2]


def test_warmup_populates_the_board_cache_for_each_city() -> None:
    assert _CACHE == {}

    with Session(engine) as session:
        warm_default_curiosities(session)

    cached = _CACHE.get(("belo_horizonte", None))
    assert cached is not None
    fingerprint, board = cached
    assert fingerprint[1] == ROW_COUNT
    assert board.transaction_count == ROW_COUNT
    assert board.months == 12


def test_board_is_recomputed_when_new_rows_arrive() -> None:
    assert _board()["transaction_count"] == ROW_COUNT

    with Session(engine) as session:
        session.add(
            _transaction(
                "9", street="RUA D", number="400", complement="AP 1",
                day=date(2025, 5, 1), value=600_000,
            )
        )
        session.commit()

    body = _board()
    assert body["transaction_count"] == ROW_COUNT + 1
    assert body["reference_date"] == "2025-05-01"
