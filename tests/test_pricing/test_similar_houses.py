"""Contexto de mercado do QuintoAndar para qualquer fonte, não só a dele."""

import pytest

from app.core.http_client import PortalBlocked
from app.models.market_comparable import MarketComparable
from app.pricing import similar_houses


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = "{}" if payload is not None else ""

    def json(self) -> dict:
        return self._payload


def _row(**overrides) -> MarketComparable:
    defaults = dict(
        source="loft", listing_id="lo-1", cidade="Belo Horizonte", rua="Rua Sao Joao",
        tipo_imovel="APARTAMENTO", lat=-19.93, lon=-43.93, bedrooms=3, bathrooms=2,
        area_util_m2=90.0, preco_total=800000.0,
    )
    defaults.update(overrides)
    return MarketComparable(**defaults)


RESUMO = {
    "summary": {
        "onMarketPriceBySquareMeter": 12280,
        "offMarketPriceBySquareMeter": 12510,
        "daysOnMarketUntilDealAverage": 119,
    },
    "availableSimilarHouses": [{"houseId": "1"}] * 10,
}


def test_the_price_band_is_deliberately_wide():
    body = similar_houses.build_body(_row(preco_total=800000.0))

    # Com faixa estreita o endpoint devolve a média de quem já está naquele
    # preço, o que é circular: pedido ±10% respondeu 12.280/m², metade do preço
    # respondeu 5.720 e o dobro respondeu 22.460. Só a faixa larga mede o
    # entorno em vez de repetir a pergunta.
    assert body["percentile10"] <= 800000 * 0.25
    assert body["percentile90"] >= 800000 * 4


def test_the_body_locates_the_unit_by_coordinates():
    body = similar_houses.build_body(_row())

    # O endpoint não pede id de anúncio, e é isso que o torna utilizável para
    # Loft e VivaReal.
    assert "id" not in body
    assert body["latitude"] == -19.93
    assert body["totalArea"] == 90


def test_a_listing_without_coordinates_cannot_be_asked():
    assert similar_houses.build_body(_row(lat=None)) is None


def test_the_summary_is_stored_on_the_row():
    row = _row()

    updated = similar_houses.similar_houses_updater(
        request_fn=lambda *a, **k: FakeResponse(200, RESUMO)
    )(row)

    assert updated is True
    assert row.similares_m2_anunciado == 12280.0
    assert row.similares_m2_negociado == 12510.0
    assert row.similares_dias_ate_negocio == 119
    assert row.similares_updated_at is not None


def test_an_empty_summary_is_settled_not_failed():
    row = _row()

    updated = similar_houses.similar_houses_updater(
        request_fn=lambda *a, **k: FakeResponse(200, {"summary": {}})
    )(row)

    # Região sem comparáveis é resposta, não falha: marca a data para não
    # perguntar de novo antes do TTL.
    assert updated is False
    assert row.similares_updated_at is not None
    assert row.similares_m2_anunciado is None


def test_a_refusal_is_reported_as_a_block():
    for status in (401, 403, 429):
        with pytest.raises(PortalBlocked):
            similar_houses.similar_houses_updater(
                request_fn=lambda *a, _s=status, **k: FakeResponse(_s)
            )(_row())
