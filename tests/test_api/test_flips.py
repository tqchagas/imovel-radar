import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ENTRADA = {
    "area_seca_m2": 92.0,
    "banheiros": 2,
    "cozinhas": 1,
    "portas": 6,
    "eletrica_completa": False,
    "hidraulica_completa_banheiro": False,
    "hidraulica_completa_cozinha": False,
    "preco_compra": 680000.0,
    "arv_total": 1080000.0,
    "meses_carrego": 7,
}


def test_preview_devolve_orcamento_dre_mao_e_matriz() -> None:
    resposta = client.post("/flips/preview", json=ENTRADA)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["orcamento"]["total"] == 41572.5
    assert corpo["dre"]["lucro_liquido"] == 227503.375
    assert corpo["dre"]["roi"] == pytest.approx(0.3003652, abs=1e-6)
    assert corpo["mao"] > ENTRADA["preco_compra"]
    assert len(corpo["matriz"]) == 9


def test_preview_traz_o_caderno_de_encargos_por_grupo() -> None:
    corpo = client.post("/flips/preview", json=ENTRADA).json()
    grupos = {g["chave"]: g for g in corpo["orcamento"]["grupos"]}
    assert set(grupos) == {"areas_secas", "banheiros", "cozinha", "geral", "retrofit"}
    assert grupos["banheiros"]["total"] == 12200.0
    portas = next(i for i in grupos["geral"]["itens"] if i["chave"] == "portas")
    assert portas["quantidade"] == 6
    assert portas["custo_unitario"] == 200.0


def test_preview_recusa_area_zerada() -> None:
    resposta = client.post("/flips/preview", json={**ENTRADA, "area_seca_m2": 0})
    assert resposta.status_code == 422


def test_preview_recusa_preco_negativo() -> None:
    resposta = client.post("/flips/preview", json={**ENTRADA, "preco_compra": -1})
    assert resposta.status_code == 422


def test_premissas_lista_rotulo_unidade_e_valor() -> None:
    corpo = client.get("/flips/premissas").json()
    por_chave = {item["chave"]: item for item in corpo}
    assert por_chave["taco"]["valor"] == 75.0
    assert por_chave["taco"]["unidade"] == "m2"
    assert "Taco" in por_chave["taco"]["rotulo"]
    assert por_chave["roi_alvo_mao"]["valor"] == 0.18


import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.models.flip_study import FlipStudy  # noqa: F401

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


@pytest.fixture(autouse=True)
def _banco():
    # O override vai na fixture, e não no módulo: com ele no topo, o último
    # arquivo de teste importado ganha e os demais falam com o banco errado.
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(engine)


ESTUDO = {
    **ENTRADA,
    "apelido": "Apto Lourdes",
    "endereco": "Rua Alvarenga Peixoto, 1420",
    "bairro": "Lourdes",
    "cidade": "belo_horizonte",
    "area_util_m2": 92.0,
    "quartos": 3,
    "status": "oportunidade",
    "origem": "manual",
}


def _premissas_caras(tmp_path, monkeypatch):
    """Aponta o carregador para um arquivo com o taco quatro vezes mais caro."""
    from app.domain import flip_premissas

    original = json.loads(flip_premissas.ARQUIVO_PADRAO.read_text(encoding="utf-8"))
    for linha in original:
        if linha["chave"] == "taco":
            linha["valor"] = 300.0
    caminho = tmp_path / "premissas.json"
    caminho.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(flip_premissas, "ARQUIVO_PADRAO", caminho)


def test_criar_estudo_devolve_a_simulacao_junto() -> None:
    resposta = client.post("/flips", json=ESTUDO)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["id"] > 0
    assert corpo["simulacao"]["dre"]["lucro_liquido"] == 227503.375
    assert corpo["bairro"] == "Lourdes"


def test_listar_traz_indicadores_recalculados() -> None:
    client.post("/flips", json=ESTUDO)
    corpo = client.get("/flips").json()
    assert len(corpo) == 1
    linha = corpo[0]
    assert linha["lucro_liquido"] == 227503.375
    assert linha["obra_total"] == 41572.5
    assert linha["mao"] > 680000.0
    assert linha["roi"] == pytest.approx(0.3003652, abs=1e-6)


def test_filtros_de_bairro_status_e_faixa_de_preco() -> None:
    client.post("/flips", json=ESTUDO)
    client.post(
        "/flips",
        json={**ESTUDO, "bairro": "Savassi", "status": "descartado", "preco_compra": 1_500_000.0},
    )
    assert len(client.get("/flips", params={"bairro": "Savassi"}).json()) == 1
    assert len(client.get("/flips", params={"status": "oportunidade"}).json()) == 1
    assert len(client.get("/flips", params={"preco_max": 700_000}).json()) == 1
    assert len(client.get("/flips", params={"preco_min": 700_000}).json()) == 1


def test_estudo_salvo_ignora_reajuste_posterior_das_premissas(tmp_path, monkeypatch) -> None:
    criado = client.post("/flips", json=ESTUDO).json()
    _premissas_caras(tmp_path, monkeypatch)
    relido = client.get(f"/flips/{criado['id']}").json()
    assert relido["simulacao"]["orcamento"]["total"] == 41572.5


def test_atualizar_premissas_traz_os_precos_novos(tmp_path, monkeypatch) -> None:
    criado = client.post("/flips", json=ESTUDO).json()
    _premissas_caras(tmp_path, monkeypatch)
    atualizado = client.patch(f"/flips/{criado['id']}", json={"atualizar_premissas": True}).json()
    # Taco de 75 para 300: +225 × 92 × 0,7 = +14.490 no subtotal, +15% em cima.
    assert atualizado["simulacao"]["orcamento"]["total"] == pytest.approx(58_236.0)


def test_patch_muda_campo_e_recalcula() -> None:
    criado = client.post("/flips", json=ESTUDO).json()
    atualizado = client.patch(f"/flips/{criado['id']}", json={"preco_compra": 600_000.0}).json()
    assert atualizado["preco_compra"] == 600_000.0
    assert atualizado["simulacao"]["dre"]["lucro_liquido"] > 227503.375


def test_excluir_some_da_lista() -> None:
    criado = client.post("/flips", json=ESTUDO).json()
    assert client.delete(f"/flips/{criado['id']}").status_code == 204
    assert client.get("/flips").json() == []


def test_id_inexistente_da_404() -> None:
    assert client.get("/flips/999").status_code == 404
    assert client.patch("/flips/999", json={"preco_compra": 1.0}).status_code == 404
    assert client.delete("/flips/999").status_code == 404


def test_preview_nao_grava_nada() -> None:
    client.post("/flips/preview", json=ENTRADA)
    assert client.get("/flips").json() == []
