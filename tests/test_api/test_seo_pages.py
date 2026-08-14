from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.transaction import Transaction

engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
SessionLocal = sessionmaker(bind=engine)


def _tx(index: int, street: str = "RUA A", number: str = "1", complement: str = "APT 1") -> Transaction:
    return Transaction(
        city="belo_horizonte",
        source_row_hash=f"seo-{street}-{number}-{complement}-{index}",
        raw_address=f"{street}, {number}",
        street=street,
        street_number=number,
        complement=complement,
        neighborhood="SAVASSI",
        built_area_acquired=80,
        acquired_fraction=1,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=500_000 + index,
        calc_base_value=500_000 + index,
        settlement_date=date(2025, 1 + (index % 6), 1),
    )


def _override_get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_module() -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        rows = [_tx(index, number=str(index % 5 + 1)) for index in range(30)]
        rows.extend([_tx(100, number="99"), _tx(101, number="99")])
        db.add_all(rows)
        db.commit()
    app.dependency_overrides[get_db] = _override_get_db


def teardown_module() -> None:
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(engine)


client = TestClient(app)


def test_neighborhood_page_renders_metrics_and_metadata_in_initial_html() -> None:
    response = client.get("/bairro/belo-horizonte/savassi/")

    assert response.status_code == 200
    assert "Preço dos imóveis em Savassi" in response.text
    assert 'name="description"' in response.text
    assert 'rel="canonical"' in response.text
    assert "quitações de ITBI" in response.text


def test_street_page_renders_address_links() -> None:
    response = client.get("/rua/belo-horizonte/rua-a/")

    assert response.status_code == 200
    assert "Imóveis na Rua A" in response.text
    assert "/imovel/belo-horizonte/rua-a/1/" in response.text


def test_property_page_renders_history_in_initial_html() -> None:
    response = client.get("/imovel/belo-horizonte/rua-a/99/apt-1/")

    assert response.status_code == 200
    assert "Histórico do imóvel na Rua A, 99" in response.text
    assert "Linha do tempo" in response.text
    assert "2" in response.text


def test_curiosities_city_hub_renders_indexable_insights() -> None:
    response = client.get("/curiosidades/belo-horizonte/")

    assert response.status_code == 200
    assert "Curiosidades de Belo Horizonte" in response.text
    assert 'rel="canonical"' in response.text
    assert "/curiosidades/belo-horizonte/maiores-vendas/" in response.text


def test_curiosity_ranking_page_renders_server_side_evidence() -> None:
    response = client.get("/curiosidades/belo-horizonte/maiores-vendas/")

    assert response.status_code == 200
    assert "Maiores vendas" in response.text
    assert "R$" in response.text


def test_curiosity_sitemap_contains_city_hub_and_eligible_rankings() -> None:
    response = client.get("/sitemap-curiosidades.xml")

    assert response.status_code == 200
    assert "/curiosidades/belo-horizonte/" in response.text
    assert "/curiosidades/belo-horizonte/maiores-vendas/" in response.text


def test_curiosity_pages_end_with_a_contextual_exploration_cta() -> None:
    hub = client.get("/curiosidades/belo-horizonte/")
    ranking = client.get("/curiosidades/belo-horizonte/maiores-vendas/")

    assert 'href="/busca?city=belo_horizonte"' in hub.text
    assert 'href="/busca?city=belo_horizonte"' in ranking.text
