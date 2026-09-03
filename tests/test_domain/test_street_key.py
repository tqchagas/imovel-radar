import pytest

from app.domain.slugs import address_key, street_key


@pytest.mark.parametrize(
    "abreviado, extenso",
    [
        ("AVE AUGUSTO DE LIMA", "Avenida Augusto de Lima"),
        ("PCA SETE DE SETEMBRO", "Praça Sete de Setembro"),
        ("ROD BR 040", "Rodovia BR 040"),
        ("ALA DAS PALMEIRAS", "Alameda das Palmeiras"),
        ("EST DO MORRO", "Estrada do Morro"),
        ("BEC DO OURO", "Beco do Ouro"),
        ("TRV SAO PAULO", "Travessa São Paulo"),
        ("R DOS AIMORES", "Rua dos Aimorés"),
        ("Av. Bias Fortes", "Avenida Bias Fortes"),
    ],
)
def test_abreviacao_do_cartorio_encontra_a_forma_do_portal(abreviado, extenso):
    assert street_key(abreviado) == street_key(extenso)


def test_a_forma_canonica_e_a_por_extenso():
    assert street_key("AVE AUGUSTO DE LIMA") == "avenida_augusto_de_lima"


def test_rua_ja_por_extenso_nao_muda():
    assert street_key("Rua dos Aimorés") == address_key("Rua dos Aimorés")


def test_nome_que_comeca_com_palavra_parecida_nao_e_expandido():
    # "Alagoas" começa com "ala" mas o tipo é a palavra inteira, não o prefixo.
    assert street_key("Rua Alagoas") == "rua_alagoas"
    # Sem tipo nenhum, o nome fica intacto.
    assert street_key("Alagoas") == "alagoas"


def test_vazio_e_none_seguem_none():
    assert street_key(None) is None
    assert street_key("") is None
    assert street_key("   ") is None
