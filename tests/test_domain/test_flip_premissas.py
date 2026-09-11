import json

import pytest

from app.domain.flip_premissas import (
    CHAVES_OBRIGATORIAS,
    PremissaAusenteError,
    carregar_premissas,
    premissas_de_valores,
)


def test_arquivo_do_repo_tem_todas_as_chaves_obrigatorias() -> None:
    premissas = carregar_premissas()
    faltando = CHAVES_OBRIGATORIAS - {item.chave for item in premissas.itens}
    assert faltando == set()


def test_valores_conhecidos_do_arquivo_do_repo() -> None:
    premissas = carregar_premissas()
    assert premissas.valor("taco") == 75.0
    assert premissas.valor("pintura_seca") == 60.0
    assert premissas.valor("coz_marcenaria") == 3000.0
    assert premissas.valor("contingencia_pct") == 0.15
    assert premissas.valor("proporcao_taco") == 0.70
    assert premissas.valor("roi_alvo_mao") == 0.18


def test_chave_desconhecida_diz_qual_chave_faltou() -> None:
    premissas = carregar_premissas()
    with pytest.raises(PremissaAusenteError) as erro:
        premissas.valor("granito_lunar")
    assert "granito_lunar" in str(erro.value)


def test_arquivo_sem_chave_obrigatoria_falha_ao_carregar(tmp_path) -> None:
    # Um arquivo capenga precisa estourar no carregamento, com o nome da chave,
    # e não virar KeyError no meio de um orçamento.
    caminho = tmp_path / "premissas.json"
    caminho.write_text(
        json.dumps([{"chave": "taco", "rotulo": "Taco", "unidade": "m2", "valor": 75}]),
        encoding="utf-8",
    )
    with pytest.raises(PremissaAusenteError) as erro:
        carregar_premissas(caminho)
    assert "contingencia_pct" in str(erro.value)


def test_premissas_de_valores_reconstroi_snapshot() -> None:
    # É assim que um estudo salvo volta a calcular com os preços de quando foi
    # salvo, mesmo que o arquivo do repo já tenha mudado.
    valores = {chave: 1.0 for chave in CHAVES_OBRIGATORIAS}
    premissas = premissas_de_valores(valores)
    assert premissas.valor("taco") == 1.0
    assert len(premissas.itens) == len(CHAVES_OBRIGATORIAS)


def test_premissas_de_valores_recusa_snapshot_incompleto() -> None:
    with pytest.raises(PremissaAusenteError):
        premissas_de_valores({"taco": 75.0})
