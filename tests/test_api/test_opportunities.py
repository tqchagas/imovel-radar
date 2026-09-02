from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.market_comparable import MarketComparable

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


client = TestClient(app)


def comparable(
    *,
    listing_id: str,
    source: str = "quintoandar",
    bairro: str = "Savassi",
    tipo_imovel: str = "APARTAMENTO",
    preco_total: float = 500000.0,
    preco_estimado: float | None = 800000.0,
    desconto_pct: float | None = 0.375,
    confianca: str | None = "alta",
    nota: int | None = 90,
    ativo: bool = True,
    last_seen_at: datetime = datetime(2026, 8, 20, 9, 42),
) -> MarketComparable:
    return MarketComparable(
        source=source,
        listing_id=listing_id,
        url=f"https://example.com/{listing_id}",
        cidade="Belo Horizonte",
        bairro=bairro,
        rua="Rua Sao Joao",
        numero="10",
        cidade_normalizada="belo_horizonte",
        bairro_normalizado=bairro.lower().replace(" ", "_"),
        rua_normalizada="rua_sao_joao",
        numero_normalizado="10",
        tipo_imovel=tipo_imovel,
        bedrooms=3,
        bathrooms=2,
        parking_spaces=1,
        area_util_m2=80.0,
        preco_total=preco_total,
        ativo=ativo,
        preco_estimado=preco_estimado,
        desconto_pct=desconto_pct,
        desconto_reais=(preco_estimado - preco_total) if preco_estimado else None,
        tipo_referencia="endereco_exato" if confianca == "alta" else "bairro_area",
        amostra_count=42,
        referencia_data_inicio=date(2024, 6, 30),
        referencia_data_fim=date(2026, 6, 30),
        confianca=confianca,
        nota=nota,
        dispersao_relativa=0.18,
        fator_calibracao=1.8,
        oportunidade_motivo="Mediana de 42 ITBIs residenciais por endereço exato.\nJanela de 24 meses.",
        first_seen_at=datetime(2026, 8, 1),
        last_seen_at=last_seen_at,
    )


@pytest.fixture(autouse=True)
def _reset_db():
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                comparable(listing_id="qa-1"),
                comparable(
                    listing_id="qa-2",
                    bairro="Lourdes",
                    preco_total=600000.0,
                    preco_estimado=700000.0,
                    desconto_pct=0.1429,
                    confianca="media",
                    nota=62,
                ),
                comparable(
                    listing_id="vr-1",
                    source="vivareal",
                    tipo_imovel="CASA",
                    preco_total=900000.0,
                    preco_estimado=1000000.0,
                    desconto_pct=0.1,
                    confianca="baixa",
                    nota=31,
                ),
                comparable(listing_id="gone", ativo=False),
                comparable(listing_id="sem-calculo", preco_estimado=None, desconto_pct=None, confianca=None, nota=None),
            ]
        )
        session.commit()
    yield
    Base.metadata.drop_all(engine)


def ids(payload) -> list[str]:
    return [item["listing_id"] for item in payload["items"]]


def test_list_returns_only_active_calculated_listings() -> None:
    response = client.get("/opportunities")

    assert response.status_code == 200
    payload = response.json()
    assert set(ids(payload)) == {"qa-1", "qa-2", "vr-1"}
    assert payload["total"] == 3


def test_list_is_sorted_by_score_by_default() -> None:
    payload = client.get("/opportunities").json()

    # The score is the ordering that makes listings comparable across tiers.
    assert ids(payload) == ["qa-1", "qa-2", "vr-1"]
    assert [item["nota"] for item in payload["items"]] == [90, 62, 31]


def test_score_filter_narrows_to_the_strongest_evidence() -> None:
    assert ids(client.get("/opportunities", params={"min_nota": 80}).json()) == ["qa-1"]
    assert ids(client.get("/opportunities", params={"min_nota": 60}).json()) == ["qa-1", "qa-2"]
    assert ids(client.get("/opportunities", params={"min_nota": 0}).json()) == ["qa-1", "qa-2", "vr-1"]


def test_score_filter_rejects_values_outside_the_scale() -> None:
    assert client.get("/opportunities", params={"min_nota": 101}).status_code == 422
    assert client.get("/opportunities", params={"min_nota": -1}).status_code == 422


def test_summary_reports_the_best_score_in_scope() -> None:
    assert client.get("/opportunities").json()["summary"]["max_nota"] == 90
    assert client.get("/opportunities", params={"neighborhood": "Lourdes"}).json()["summary"]["max_nota"] == 62


def test_score_context_is_exposed_for_each_listing() -> None:
    item = client.get("/opportunities").json()["items"][0]

    # Without these the score is a number nobody can argue with.
    assert item["dispersao_relativa"] == pytest.approx(0.18)
    assert item["fator_calibracao"] == pytest.approx(1.8)


def test_list_accepts_alternative_sorts() -> None:
    assert ids(client.get("/opportunities", params={"sort": "desconto_asc"}).json()) == [
        "vr-1",
        "qa-2",
        "qa-1",
    ]
    assert ids(client.get("/opportunities", params={"sort": "preco_asc"}).json()) == [
        "qa-1",
        "qa-2",
        "vr-1",
    ]
    assert ids(client.get("/opportunities", params={"sort": "preco_desc"}).json()) == [
        "vr-1",
        "qa-2",
        "qa-1",
    ]


def test_unknown_sort_is_rejected() -> None:
    assert client.get("/opportunities", params={"sort": "nope"}).status_code == 400


def test_filters_narrow_the_result() -> None:
    assert ids(client.get("/opportunities", params={"source": "vivareal"}).json()) == ["vr-1"]
    assert ids(client.get("/opportunities", params={"neighborhood": "Lourdes"}).json()) == ["qa-2"]
    assert ids(client.get("/opportunities", params={"neighborhood": "LOURDES"}).json()) == ["qa-2"]
    assert ids(client.get("/opportunities", params={"tipo_imovel": "CASA"}).json()) == ["vr-1"]
    assert ids(client.get("/opportunities", params={"confianca": "alta"}).json()) == ["qa-1"]
    assert ids(client.get("/opportunities", params={"min_desconto_pct": 0.15}).json()) == ["qa-1"]
    assert ids(client.get("/opportunities", params={"city": "belo_horizonte"}).json()) == [
        "qa-1",
        "qa-2",
        "vr-1",
    ]
    assert client.get("/opportunities", params={"city": "contagem"}).json()["total"] == 0


def test_min_confianca_filters_by_confidence_order() -> None:
    payload = client.get("/opportunities", params={"min_confianca": "media"}).json()

    assert set(ids(payload)) == {"qa-1", "qa-2"}


def test_pagination_is_stable() -> None:
    first = client.get("/opportunities", params={"page": 1, "page_size": 2}).json()
    second = client.get("/opportunities", params={"page": 2, "page_size": 2}).json()

    assert ids(first) == ["qa-1", "qa-2"]
    assert ids(second) == ["vr-1"]
    assert first["total"] == 3
    assert first["page_size"] == 2
    assert second["page"] == 2


def test_summary_reports_totals_and_last_collection() -> None:
    payload = client.get("/opportunities").json()

    assert payload["summary"]["total"] == 3
    assert payload["summary"]["max_desconto_pct"] == pytest.approx(0.375)
    assert payload["summary"]["last_collected_at"].startswith("2026-08-20T09:42")
    assert payload["summary"]["reference_date"] == "2026-06-30"


def test_summary_follows_the_active_filters() -> None:
    payload = client.get("/opportunities", params={"source": "vivareal"}).json()

    assert payload["summary"]["total"] == 1
    assert payload["summary"]["max_desconto_pct"] == pytest.approx(0.1)


def test_item_exposes_the_calculation_context() -> None:
    item = client.get("/opportunities", params={"source": "quintoandar", "confianca": "alta"}).json()["items"][0]

    assert item["preco_anunciado"] == pytest.approx(500000.0)
    assert item["preco_estimado"] == pytest.approx(800000.0)
    assert item["desconto_reais"] == pytest.approx(300000.0)
    assert item["tipo_referencia"] == "endereco_exato"
    assert item["amostra_count"] == 42
    assert item["referencia_data_inicio"] == "2024-06-30"
    assert item["confianca"] == "alta"
    assert item["quartos"] == 3
    assert item["banheiros"] == 2
    assert item["vagas"] == 1
    assert item["url"] == "https://example.com/qa-1"
    assert len(item["motivos"]) == 2


def test_detail_returns_a_single_opportunity() -> None:
    listed = client.get("/opportunities").json()["items"][0]

    response = client.get(f"/opportunities/{listed['id']}")

    assert response.status_code == 200
    assert response.json()["listing_id"] == "qa-1"


def test_detail_hides_inactive_and_uncalculated_listings() -> None:
    with Session(engine) as session:
        hidden = [
            session.query(MarketComparable).filter_by(listing_id="gone").one().id,
            session.query(MarketComparable).filter_by(listing_id="sem-calculo").one().id,
        ]

    for listing_id in hidden:
        assert client.get(f"/opportunities/{listing_id}").status_code == 404
    assert client.get("/opportunities/999999").status_code == 404


def test_the_listing_carries_the_quintoandar_estimate() -> None:
    with Session(engine) as session:
        row = session.query(MarketComparable).filter_by(listing_id="qa-1").one()
        row.price_suggestion_price = 700000.0
        row.qpreco_desconto_pct = 0.2857
        row.nota_qpreco = 74
        row.nota_itbi = 90
        session.commit()

    response = client.get("/opportunities")

    item = next(i for i in response.json()["items"] if i["listing_id"] == "qa-1")
    assert item["qpreco_estimado"] == 700000.0
    assert item["qpreco_desconto_pct"] == pytest.approx(0.2857)
    assert item["nota_qpreco"] == 74
    assert item["nota_itbi"] == 90


def test_a_listing_without_a_quintoandar_estimate_reports_null() -> None:
    response = client.get("/opportunities")

    item = next(i for i in response.json()["items"] if i["listing_id"] == "vr-1")
    assert item["qpreco_estimado"] is None
    assert item["nota_qpreco"] is None


def _mark_qpreco(listing_ids: tuple[str, ...]) -> None:
    with Session(engine) as session:
        for listing_id in listing_ids:
            row = session.query(MarketComparable).filter_by(listing_id=listing_id).one()
            row.price_suggestion_price = 700000.0
            row.nota_qpreco = 74
        session.commit()


def test_the_listing_can_be_narrowed_to_rows_with_a_quintoandar_estimate() -> None:
    _mark_qpreco(("qa-1",))

    payload = client.get("/opportunities", params={"com_qpreco": "true", "min_nota": 0}).json()

    assert [item["listing_id"] for item in payload["items"]] == ["qa-1"]
    assert payload["total"] == 1


def test_the_listing_can_be_narrowed_to_rows_still_missing_an_estimate() -> None:
    _mark_qpreco(("qa-1",))

    payload = client.get("/opportunities", params={"com_qpreco": "false", "min_nota": 0}).json()

    ids = sorted(item["listing_id"] for item in payload["items"])
    # A listing QuintoAndar refused to price has no stored value either, so it
    # belongs with the ones still missing an estimate.
    assert ids == ["qa-2", "vr-1"]


def test_without_the_flag_every_row_is_listed() -> None:
    _mark_qpreco(("qa-1",))

    payload = client.get("/opportunities", params={"min_nota": 0}).json()

    assert payload["total"] == 3


def test_the_listing_reports_how_long_it_has_been_advertised() -> None:
    with Session(engine) as session:
        row = session.query(MarketComparable).filter_by(listing_id="qa-1").one()
        row.anunciado_em = datetime(2025, 9, 13)
        row.condominium_value = 1300.0
        row.iptu_value = 478.0
        session.commit()

    payload = client.get("/opportunities").json()

    item = next(i for i in payload["items"] if i["listing_id"] == "qa-1")
    assert item["anunciado_em"].startswith("2025-09-13")
    assert item["condominio"] == 1300.0
    assert item["iptu"] == 478.0


def test_a_listing_without_a_publication_date_reports_null() -> None:
    payload = client.get("/opportunities").json()

    item = next(i for i in payload["items"] if i["listing_id"] == "vr-1")
    assert item["anunciado_em"] is None


def test_the_listing_carries_the_neighbourhood_context() -> None:
    with Session(engine) as session:
        row = session.query(MarketComparable).filter_by(listing_id="qa-1").one()
        row.similares_m2_anunciado = 12280.0
        row.similares_m2_negociado = 12510.0
        row.similares_dias_ate_negocio = 119
        session.commit()

    payload = client.get("/opportunities").json()

    item = next(i for i in payload["items"] if i["listing_id"] == "qa-1")
    assert item["similares_m2_anunciado"] == 12280.0
    assert item["similares_m2_negociado"] == 12510.0
    assert item["similares_dias_ate_negocio"] == 119
