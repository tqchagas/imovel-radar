"""A forma da rua que a busca compara: sem acento, sem pontuação, com espaço."""

from app.domain.slugs import street_search_text


def test_acento_some():
    assert street_search_text("Rua José Bonifácio") == "rua jose bonifacio"


def test_caixa_nao_importa():
    assert street_search_text("RUA SÃO JOÃO") == street_search_text("rua sao joao")


def test_abreviacao_do_cartorio_encontra_a_forma_por_extenso():
    assert street_search_text("AVE AUGUSTO DE LIMA") == street_search_text(
        "Avenida Augusto de Lima"
    )


def test_pontuacao_e_curinga_de_like_somem():
    # Sem isso, `%` e `_` digitados pelo usuário viram curinga no LIKE.
    assert street_search_text("R. dos Aimorés 100%_") == "rua dos aimores 100"


def test_vazio_vira_none():
    assert street_search_text("   ") is None
    assert street_search_text(None) is None
