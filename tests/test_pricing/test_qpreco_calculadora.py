from datetime import date

import pytest

from app.core.http_client import PortalBlocked
from app.pricing.qpreco_calculadora import (
    EstimateInput,
    QprecoUnavailable,
    fetch_comparables,
    fetch_estimate,
)

ENTRADA = EstimateInput(
    address="Rua Gonçalves Dias", address_number=865, neighborhood="Funcionários",
    city="Belo Horizonte", state="MG", latitude=-19.932468, longitude=-43.933033,
    total_area=295, bedroom_count=4, bathroom_count=3, suites_count=2,
    parking_slots=2, floor=8, condominium_per_month=1500, iptu_per_year=4800,
)

ESTIMATE = {
    "suggestedPrice": 4513000, "suggestedLowerBoundPrice": 3817000,
    "suggestedUpperBoundPrice": 5112000, "lowerBoundLimit": 2903000,
    "upperBoundLimit": 6046500, "predictionCertainty": "low",
    "percentiles": {"10": 2903000, "20": 0, "50": 4513000, "90": 6046500},
}

SIMILARES = {
    "summary": {"onMarketPriceBySquareMeter": 13510,
                "offMarketPriceBySquareMeter": 13120,
                "daysOnMarketUntilDealAverage": 179},
    "unavailableSimilarHouses": [{
        "houseId": 895356778, "price": 3100000, "priceM2": 10333, "totalArea": 300,
        "bedroomCount": 4, "parkingSlots": 2, "distance": 0.4837526329071326,
        "lastTimeOnMarket": "2026-04-17T11:03:09.1111", "address": "Rua Gonçalves Dias",
        "neighborhood": "Funcionários", "city": "Belo Horizonte", "sameCondo": False,
    }, {
        "houseId": 2, "price": 2900000, "priceM2": 10984, "totalArea": 264,
        "bedroomCount": None, "parkingSlots": 1, "distance": 0.92,
        "lastTimeOnMarket": None, "address": "Rua Espírito Santo",
        "neighborhood": "Centro", "city": "Belo Horizonte", "sameCondo": True,
    }],
    "availableSimilarHouses": [],
    "negotiatedInTheSameCondo": [],
}


class _Resposta:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _responde(payload, status=200, registro=None):
    def request(method, url, **kwargs):
        if registro is not None:
            registro.append({"url": url, "body": kwargs.get("json_body")})
        return _Resposta(status, payload)

    return request


def test_le_a_faixa_os_limites_e_a_certeza():
    """`predictionCertainty` é sinal de primeira classe: medido ao vivo, volta
    "low" em Funcionários e "medium" em Vila Madalena."""
    e = fetch_estimate(ENTRADA, request_fn=_responde(ESTIMATE))

    assert e.suggested_price == 4513000
    assert (e.lower_bound, e.upper_bound) == (3817000, 5112000)
    assert (e.limit_lower, e.limit_upper) == (2903000, 6046500)
    assert e.certainty == "low"


def test_descarta_os_decis_zerados():
    """O portal devolve 0 nas casas que não calcula — 20, 40, 60 e 80 vieram
    zeradas em todas as consultas medidas. Guardar zero é guardar mentira."""
    e = fetch_estimate(ENTRADA, request_fn=_responde(ESTIMATE))

    assert 20 not in e.percentiles
    assert e.percentiles[50] == 4513000


def test_manda_a_area_util_e_o_numero_no_corpo():
    registro = []
    fetch_estimate(ENTRADA, request_fn=_responde(ESTIMATE, registro=registro))
    corpo = registro[0]["body"]

    assert corpo["totalArea"] == 295
    assert corpo["addressNumber"] == 865
    assert corpo["latitude"] == -19.932468
    assert corpo["businessContext"] == "SALE"


def test_nunca_chama_save_lead():
    """A tela do portal registra um lead num terceiro POST. Ele é separado e
    pulável, e não chamá-lo é o desenho."""
    registro = []
    e = fetch_estimate(ENTRADA, request_fn=_responde(ESTIMATE, registro=registro))
    fetch_comparables(ENTRADA, e, request_fn=_responde(SIMILARES, registro=registro))

    assert not any("save-lead" in r["url"] for r in registro)


def test_sem_preco_e_indisponivel():
    """Sem coordenada o portal responde 200 dizendo que não conseguiu — a mesma
    resposta que dá para imóvel atípico. Inventar número seria pior."""
    with pytest.raises(QprecoUnavailable):
        fetch_estimate(ENTRADA, request_fn=_responde({"suggestedPrice": None}))


def test_bloqueio_do_portal_aborta():
    for status in (401, 403, 429):
        with pytest.raises(PortalBlocked):
            fetch_estimate(ENTRADA, request_fn=_responde({}, status=status))


def test_comparaveis_trazem_preco_de_transacao_com_data():
    e = fetch_estimate(ENTRADA, request_fn=_responde(ESTIMATE))
    c = fetch_comparables(ENTRADA, e, request_fn=_responde(SIMILARES))

    assert len(c.sold) == 2
    primeiro = c.sold[0]
    assert primeiro.price == 3100000
    assert primeiro.price_m2 == 10333
    assert primeiro.sold_at == date(2026, 4, 17)
    assert primeiro.distance_km == pytest.approx(0.4838, abs=1e-4)
    assert primeiro.same_condo is False
    assert c.days_until_deal == 179


def test_comparavel_sem_data_ou_sem_quartos_sobrevive():
    """`bedroomCount` volta nulo na maioria dos vendidos; descartá-los
    esvaziaria a amostra."""
    e = fetch_estimate(ENTRADA, request_fn=_responde(ESTIMATE))
    c = fetch_comparables(ENTRADA, e, request_fn=_responde(SIMILARES))

    assert c.sold[1].sold_at is None
    assert c.sold[1].bedroom_count is None
    assert c.sold[1].same_condo is True


def test_a_faixa_enviada_e_a_da_propria_estimativa():
    """A faixa filtra os comparáveis do lado do portal; mandar a da estimativa
    é o que mantém a resposta comparável com a que o site mostraria."""
    registro = []
    e = fetch_estimate(ENTRADA, request_fn=_responde(ESTIMATE))
    fetch_comparables(ENTRADA, e, request_fn=_responde(SIMILARES, registro=registro))

    assert registro[0]["body"]["percentile10"] == 2903000
    assert registro[0]["body"]["percentile90"] == 6046500
