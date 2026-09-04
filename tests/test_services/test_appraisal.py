import json
from datetime import datetime, timedelta

import pytest

from app.core.http_client import PortalBlocked
from app.models.auction_property import AuctionAppraisal, AuctionProperty
from app.models.portal_building import PortalBuilding
from app.models.registry_address import RegistryAddress
from app.services.appraisal import (
    FONTE_CADASTRO,
    FONTE_PORTAL,
    avaliar_imovel,
    sugerir_coordenada,
)

ESTIMATE = {
    "suggestedPrice": 4513000, "suggestedLowerBoundPrice": 3817000,
    "suggestedUpperBoundPrice": 5112000, "lowerBoundLimit": 2903000,
    "upperBoundLimit": 6046500, "predictionCertainty": "low",
    "percentiles": {"10": 2903000, "20": 0, "50": 4513000},
}
SIMILARES = {
    "summary": {"onMarketPriceBySquareMeter": 13510, "offMarketPriceBySquareMeter": 13120,
                "daysOnMarketUntilDealAverage": 179},
    "unavailableSimilarHouses": [
        {"houseId": i, "price": 4_500_000, "priceM2": 15254, "totalArea": 295,
         "bedroomCount": 4, "parkingSlots": 2, "distance": 0.3,
         "lastTimeOnMarket": "2026-04-17T11:03:09", "address": "Rua X",
         "neighborhood": "Y", "city": "Belo Horizonte", "sameCondo": False}
        for i in range(4)
    ],
    "availableSimilarHouses": [],
}


class _Resposta:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _portal(chamadas=None, bloqueia=False):
    def request(method, url, **kwargs):
        if chamadas is not None:
            chamadas.append(url)
        if bloqueia:
            return _Resposta(429, {})
        return _Resposta(200, SIMILARES if "similar-houses" in url else ESTIMATE)

    return request


def _imovel(db, **extra):
    valores = dict(
        address="Rua Gonçalves Dias", address_number="865", neighborhood="Funcionários",
        city="Belo Horizonte", state="MG", latitude=-19.932468, longitude=-43.933033,
        total_area=295, bedroom_count=4, bathroom_count=3, parking_slots=2,
    )
    valores.update(extra)
    imovel = AuctionProperty(**valores)
    db.add(imovel)
    db.commit()
    db.refresh(imovel)
    return imovel


def test_sugere_o_ponto_do_portal_antes_do_lote_da_prefeitura(db_session):
    """O ponto do condomínio é o que o próprio QuintoAndar usa para o prédio, e
    é contra ele que o modelo foi indexado — seis metros de diferença moveram a
    estimativa em 18,4%."""
    db_session.add(PortalBuilding(
        source="quintoandar", external_id="abc", url="https://q/x", city="belo_horizonte",
        street_key="rua_goncalves_dias", number_key="865", lat=-19.932468, lon=-43.933033))
    db_session.add(RegistryAddress(
        city="belo_horizonte", street="R", street_number="865",
        street_key="rua_goncalves_dias", number_key="865", construction_type="AP",
        lat=-19.932521, lon=-43.933081))
    db_session.commit()

    achado = sugerir_coordenada(
        db_session, city="Belo Horizonte", street="Rua Gonçalves Dias", number="865")
    assert achado == (-19.932468, -43.933033, FONTE_PORTAL)


def test_cai_para_o_cadastro_quando_o_portal_nao_conhece(db_session):
    db_session.add(RegistryAddress(
        city="belo_horizonte", street="R", street_number="865",
        street_key="rua_goncalves_dias", number_key="865", construction_type="AP",
        lat=-19.932521, lon=-43.933081))
    db_session.commit()

    achado = sugerir_coordenada(
        db_session, city="Belo Horizonte", street="Rua Gonçalves Dias", number="865")
    assert achado == (-19.932521, -43.933081, FONTE_CADASTRO)


def test_nao_sugere_coordenada_fora_de_bh(db_session):
    """Sem base local a resposta honesta é não ter resposta: chutar aqui é o
    modo de falha que este desenho existe para evitar."""
    assert sugerir_coordenada(
        db_session, city="São Paulo", street="Rua Harmonia", number="1000") is None


def test_avaliar_grava_as_duas_leituras_e_os_comparaveis(db_session):
    imovel = _imovel(db_session)
    a = avaliar_imovel(db_session, imovel, request_fn=_portal())

    assert a.preco_qpreco == 4513000
    assert a.certeza == "low"
    assert a.comparaveis_usados == 4
    assert a.preco_vendidos == pytest.approx(15254 * 295)
    assert a.divergencia_pct is not None
    # Os três preços do portal: rápido, sugerido e esperando comprador.
    assert (a.preco_rapido, a.preco_qpreco, a.preco_devagar) == (3817000, 4513000, 5112000)
    assert (a.limite_inferior, a.limite_superior) == (2903000, 6046500)
    assert len(a.comparaveis_json) == 4
    assert a.comparaveis_json[0]["sold_at"] == "2026-04-17"


def test_avaliar_respeita_o_ttl(db_session):
    imovel = _imovel(db_session)
    chamadas = []
    avaliar_imovel(db_session, imovel, request_fn=_portal(chamadas))
    avaliar_imovel(db_session, imovel, request_fn=_portal(chamadas))

    assert len(chamadas) == 2  # estimate + similar-houses, uma vez só
    assert db_session.query(AuctionAppraisal).count() == 1


def test_force_reconsulta_dentro_do_ttl(db_session):
    imovel = _imovel(db_session)
    chamadas = []
    avaliar_imovel(db_session, imovel, request_fn=_portal(chamadas))
    avaliar_imovel(db_session, imovel, force=True, request_fn=_portal(chamadas))

    assert len(chamadas) == 4
    assert db_session.query(AuctionAppraisal).count() == 2


def test_avaliacao_vencida_e_reconsultada(db_session):
    imovel = _imovel(db_session)
    chamadas = []
    avaliar_imovel(db_session, imovel, request_fn=_portal(chamadas),
                   now=datetime(2026, 1, 1))
    avaliar_imovel(db_session, imovel, request_fn=_portal(chamadas),
                   now=datetime(2026, 3, 1))
    assert len(chamadas) == 4


def test_portal_bloqueado_grava_o_erro_em_vez_de_estourar(db_session):
    """Guardar a falha evita reconsultar em loop e deixa a tela dizer o que houve."""
    imovel = _imovel(db_session)
    a = avaliar_imovel(db_session, imovel, request_fn=_portal(bloqueia=True))

    assert a.preco_qpreco is None
    assert "429" in a.erro
