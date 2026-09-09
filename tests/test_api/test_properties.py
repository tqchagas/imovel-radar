from datetime import date

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


def _add_tx(session: Session, **kwargs) -> Transaction:
    defaults = dict(
        city="belo_horizonte",
        source_row_hash=kwargs.pop("source_row_hash", f"hash-{kwargs.get('id', 'x')}"),
        raw_address="AVE AUGUSTO DE LIMA 134 - APT 1201 - CENTRO",
        street="AVE AUGUSTO DE LIMA",
        street_number="134",
        complement="APT 1201",
        postal_code="30190-001",
        neighborhood="CENTRO",
        construction_year=1965,
        land_area=1080.0,
        built_area_acquired=47.25,
        acquired_area_total=47.25,
        finish_standard="P3",
        acquired_fraction=0.00333,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=270000.0,
        calc_base_value=270000.0,
        zoning="ZHIP",
        settlement_date=date(2020, 1, 1),
    )
    defaults.update(kwargs)
    tx = Transaction(**defaults)
    session.add(tx)
    return tx


@pytest.fixture(autouse=True)
def _reset_db():
    # Re-bind for this module: other API test modules also override get_db.
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _add_tx(
            session,
            source_row_hash="h1",
            complement="APT 1201",
            declared_value=200000.0,
            calc_base_value=200000.0,
            acquired_fraction=0.003,
            settlement_date=date(2018, 6, 1),
        )
        _add_tx(
            session,
            source_row_hash="h2",
            complement="APTO 1201",  # same unit, different spelling
            declared_value=300000.0,
            calc_base_value=310000.0,
            acquired_fraction=0.003,
            settlement_date=date(2022, 6, 1),
        )
        _add_tx(
            session,
            source_row_hash="h3",
            complement="APT 999",
            declared_value=150000.0,
            settlement_date=date(2021, 1, 1),
        )
        _add_tx(
            session,
            source_row_hash="h4",
            street="RUA CASA",
            street_number="10",
            complement=None,
            raw_address="RUA CASA 10",
            declared_value=400000.0,
            settlement_date=date(2019, 1, 1),
        )
        _add_tx(
            session,
            source_row_hash="h5",
            street="RUA CASA",
            street_number="10",
            complement=None,
            raw_address="RUA CASA 10 later",
            declared_value=500000.0,
            settlement_date=date(2023, 1, 1),
        )
        session.commit()
    yield
    Base.metadata.drop_all(engine)


client = TestClient(app)


def test_get_property_groups_complement_variants() -> None:
    response = client.get(
        "/properties",
        params={
            "city": "belo_horizonte",
            "street": "AVE AUGUSTO DE LIMA",
            "street_number": "134",
            "complement": "AP 1201",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["transaction_count"] == 2
    assert body["complement_normalized"] == "APT 1201"
    assert body["summary"]["appreciation_pct"] == 50.0
    assert len(body["timeline"]) == 2
    assert body["timeline"][0]["declared_value"] == 200000.0
    assert body["timeline"][1]["declared_value"] == 300000.0


def test_get_property_excludes_other_units() -> None:
    response = client.get(
        "/properties",
        params={
            "city": "belo_horizonte",
            "street": "AVE AUGUSTO DE LIMA",
            "street_number": "134",
            "complement": "APT 1201",
        },
    )
    comps = {t["complement"] for t in response.json()["transactions"]}
    assert "APT 999" not in comps


def test_get_property_lot_level_without_complement() -> None:
    response = client.get(
        "/properties",
        params={
            "city": "belo_horizonte",
            "street": "RUA CASA",
            "street_number": "10",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["complement"] is None
    assert body["summary"]["transaction_count"] == 2
    assert body["summary"]["appreciation_pct"] == 25.0


def test_get_property_by_transaction_resolves_unit() -> None:
    listing = client.get("/transactions", params={"street": "AUGUSTO"}).json()
    # Find APT 1201 row
    tx = next(i for i in listing["items"] if i["complement"] in ("APT 1201", "APTO 1201"))
    response = client.get(f"/properties/by-transaction/{tx['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["transaction_count"] == 2
    assert body["street"] == "AVE AUGUSTO DE LIMA"


def test_get_property_accepts_slugs() -> None:
    response = client.get(
        "/properties",
        params={
            "city": "belo-horizonte",
            "street": "ave-augusto-de-lima",
            "street_number": "134",
            "complement": "apt-1201",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["transaction_count"] == 2
    assert body["street"] == "AVE AUGUSTO DE LIMA"
    assert body["city"] == "belo_horizonte"


def test_get_property_404() -> None:
    response = client.get(
        "/properties",
        params={
            "city": "belo_horizonte",
            "street": "RUA INEXISTENTE",
            "street_number": "1",
        },
    )
    assert response.status_code == 404


def test_imovel_page_served() -> None:
    response = client.get("/imovel")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert b"Linha do tempo" in response.content


from app.models.monetary_index import SERIE_IPCA, MonetaryIndex
from app.services import deflator as servico_deflator

PARAMS_APT = {
    "city": "belo_horizonte",
    "street": "AVE AUGUSTO DE LIMA",
    "street_number": "134",
    "complement": "AP 1201",
}


def _semear_ipca() -> None:
    """De jun/2018 a jun/2022 o índice acumula 50%: fator 1,5."""
    servico_deflator.invalidar_cache()
    with Session(engine) as session:
        session.add_all(
            [
                MonetaryIndex(series=SERIE_IPCA, competencia=date(2018, 6, 1), variacao_pct=0.0),
                MonetaryIndex(series=SERIE_IPCA, competencia=date(2022, 6, 1), variacao_pct=50.0),
            ]
        )
        session.commit()


def test_a_linha_do_tempo_traz_o_valor_em_reais_de_hoje() -> None:
    _semear_ipca()
    body = client.get("/properties", params=PARAMS_APT).json()
    por_data = {p["settlement_date"]: p for p in body["timeline"]}
    assert por_data["2018-06-01"]["declared_value_corrected"] == pytest.approx(300000.0)
    assert por_data["2022-06-01"]["declared_value_corrected"] == pytest.approx(300000.0)
    assert body["correction_reference"] == "2022-06-01"


def test_a_valorizacao_real_desconta_a_inflacao() -> None:
    # +50% nominal num período de +50% de índice é 0% real: o imóvel só
    # acompanhou o dinheiro. É essa leitura que o nominal esconde.
    _semear_ipca()
    resumo = client.get("/properties", params=PARAMS_APT).json()["summary"]
    assert resumo["appreciation_pct"] == pytest.approx(50.0)
    assert resumo["appreciation_real_pct"] == pytest.approx(0.0, abs=0.01)


def test_sem_serie_gravada_o_nominal_fica_intacto() -> None:
    servico_deflator.invalidar_cache()
    body = client.get("/properties", params=PARAMS_APT).json()
    assert body["summary"]["appreciation_pct"] == pytest.approx(50.0)
    assert body["summary"]["appreciation_real_pct"] is None
    assert body["correction_reference"] is None
    assert body["timeline"][0]["declared_value_corrected"] is None


def test_quitacao_em_mes_fora_da_serie_nao_e_corrigida() -> None:
    # A unidade APT 999 quitou em jan/2021, mês que a série semeada não tem.
    _semear_ipca()
    body = client.get(
        "/properties", params={**PARAMS_APT, "complement": "APT 999"}
    ).json()
    assert body["timeline"][0]["declared_value_corrected"] is None
