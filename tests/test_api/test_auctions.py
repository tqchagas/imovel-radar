from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auction_property import AuctionProperty  # noqa: F401
from app.models.portal_building import PortalBuilding
from app.models.registry_address import RegistryAddress  # noqa: F401

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


@pytest.fixture(autouse=True)
def _banco():
    # O override vai na fixture, e não no módulo: com ele no topo, o último
    # arquivo de teste importado ganha e os demais falam com o banco errado.
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(engine)


IMOVEL = {
    "address": "Rua Gonçalves Dias", "address_number": "865",
    "neighborhood": "Funcionários", "city": "Belo Horizonte", "state": "MG",
    "latitude": -19.932468, "longitude": -43.933033,
    "total_area": 295, "bedroom_count": 4, "bathroom_count": 3, "parking_slots": 2,
}


def test_cria_com_coordenada_informada_e_marca_a_fonte():
    r = client.post("/auctions", json=IMOVEL)
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["coordenada_fonte"] == "manual"
    assert corpo["coordenada_rotulo"] == "informada por você"
    assert corpo["avaliacao"] is None


def test_sem_coordenada_e_sem_base_local_recusa():
    """Inventar coordenada é o modo de falha que este desenho evita: seis
    metros já moveram a estimativa em 18,4%."""
    payload = {**IMOVEL, "city": "São Paulo"}
    payload.pop("latitude")
    payload.pop("longitude")

    r = client.post("/auctions", json=payload)
    assert r.status_code == 422
    assert "coordenada" in r.json()["detail"]


def test_sem_coordenada_usa_a_sugestao_de_bh():
    db = TestSessionLocal()
    db.add(PortalBuilding(
        source="quintoandar", external_id="abc", url="https://q/x", city="belo_horizonte",
        street_key="rua_goncalves_dias", number_key="865", lat=-19.932468, lon=-43.933033))
    db.commit()
    db.close()

    payload = {k: v for k, v in IMOVEL.items() if k not in ("latitude", "longitude")}
    r = client.post("/auctions", json=payload)

    assert r.status_code == 201
    assert r.json()["coordenada_fonte"] == "portal"


def test_sugestao_de_coordenada_fora_de_bh_e_404():
    r = client.get("/auctions/coordenada", params={"city": "São Paulo", "street": "Rua Harmonia"})
    assert r.status_code == 404


def test_listagem_esconde_leilao_ja_passado_mas_nao_apaga():
    client.post("/auctions", json={**IMOVEL, "data_leilao": str(date.today() - timedelta(days=1))})
    client.post("/auctions", json={**IMOVEL, "data_leilao": str(date.today() + timedelta(days=10))})

    assert len(client.get("/auctions").json()) == 1
    assert len(client.get("/auctions", params={"incluir_passados": True}).json()) == 2


def test_editar_coordenada_marca_como_manual():
    criado = client.post("/auctions", json=IMOVEL).json()
    r = client.patch(f"/auctions/{criado['id']}", json={"latitude": -19.9, "longitude": -43.9})

    assert r.status_code == 200
    assert r.json()["coordenada_fonte"] == "manual"


def test_remover_leva_o_historico_junto():
    criado = client.post("/auctions", json=IMOVEL).json()
    assert client.delete(f"/auctions/{criado['id']}").status_code == 204
    assert client.get(f"/auctions/{criado['id']}/historico").status_code == 404


def test_pagina_do_leilao_responde():
    r = client.get("/leilao")
    assert r.status_code == 200
    assert "noindex" in r.text
