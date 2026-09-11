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
