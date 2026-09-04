from datetime import date

import pytest

from app.models.registry_address import RegistryAddress
from app.ingestion.pbh_registry import aggregate
from app.services import registry_sync


def _endereco(db, source_date: date | None, numero: str = "10") -> RegistryAddress:
    row = RegistryAddress(
        city="belo_horizonte",
        street="AVE AUGUSTO DE LIMA",
        street_number=numero,
        street_key="avenida_augusto_de_lima",
        number_key=numero,
        construction_type="AP",
        units_count=1,
        source_date=source_date,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def recursos(monkeypatch):
    """Finge o que o CKAN publica, sem tocar na rede."""

    def _publicar(stamp: str):
        monkeypatch.setattr(
            registry_sync,
            "discover_resources",
            lambda *a, **k: {"norte": (stamp, "https://exemplo/norte.csv")},
        )

    return _publicar


def test_pula_quando_o_gravado_ja_e_o_publicado(db_session, recursos, monkeypatch):
    _endereco(db_session, date(2026, 7, 1))
    recursos("20260701")
    monkeypatch.setattr(
        registry_sync, "stream_resource", lambda *a, **k: pytest.fail("não devia baixar")
    )

    resumo = registry_sync.sync_registry(db_session, city="belo_horizonte", skip_if_current=True)

    assert resumo["enderecos"] == 0
    assert "pulado" in resumo


def test_baixa_quando_o_ckan_publica_extracao_mais_nova(db_session, recursos, monkeypatch):
    _endereco(db_session, date(2026, 7, 1))
    recursos("20260801")
    baixou = []
    monkeypatch.setattr(
        registry_sync, "stream_resource", lambda *a, **k: baixou.append(1) or iter(())
    )

    registry_sync.sync_registry(db_session, city="belo_horizonte", skip_if_current=True)

    assert baixou == [1]


def test_baixa_quando_nao_ha_nada_gravado(db_session, recursos, monkeypatch):
    recursos("20260701")
    baixou = []
    monkeypatch.setattr(
        registry_sync, "stream_resource", lambda *a, **k: baixou.append(1) or iter(())
    )

    registry_sync.sync_registry(db_session, city="belo_horizonte", skip_if_current=True)

    assert baixou == [1]


def test_sem_a_opcao_baixa_sempre(db_session, recursos, monkeypatch):
    _endereco(db_session, date(2026, 7, 1))
    recursos("20260701")
    baixou = []
    monkeypatch.setattr(
        registry_sync, "stream_resource", lambda *a, **k: baixou.append(1) or iter(())
    )

    registry_sync.sync_registry(db_session, city="belo_horizonte")

    assert baixou == [1]


def _economia(area, numero="100"):
    """Uma economia tributária do CSV da prefeitura, com o mínimo que importa."""
    return {
        "TIPO_CONSTRUTIVO": "APARTAMENTO",
        "TIPO_LOGRADOURO": "RUA",
        "NOME_LOGRADOURO": "DOS TIMBIRAS",
        "NUMERO_IMOVEL": numero,
        "AREA_CONSTRUCAO": str(area),
        "PADRAO_ACABAMENTO": "P4",
        "TIPO_OCUPACAO": "RESIDENCIAL",
        "GEOMETRIA": "",
        "CEP": "30140-060",
    }


def test_perfil_tem_onze_decis_do_menor_ao_maior():
    """O casamento por posto precisa do formato do prédio, não só da mediana:
    a mediana compara a cobertura com o quarto e sala."""
    areas = [90, 95, 100, 140, 145, 150, 205, 210, 215, 300]
    linhas = list(aggregate(_economia(a) for a in areas))

    perfil = linhas[0].unit_area_profile
    assert perfil is not None
    assert len(perfil) == 11
    assert perfil[0] == 90.0
    assert perfil[-1] == 300.0
    assert perfil == sorted(perfil)


def test_perfil_e_nulo_abaixo_de_quatro_unidades():
    """Abaixo de quatro unidades não há quartil, e três apartamentos não são
    evidência de formato nenhum — o mesmo piso que a dispersão já usa."""
    linhas = list(aggregate(_economia(a) for a in [90, 95, 100]))
    assert linhas[0].unit_area_profile is None


def test_perfil_ignora_economia_sem_area():
    """A linha sem área não descreve unidade nenhuma e não pode entrar no posto."""
    linhas = list(aggregate(
        [_economia(90), _economia(95), _economia(100), _economia(140), _economia("")]
    ))
    perfil = linhas[0].unit_area_profile
    assert perfil is not None
    assert perfil[0] == 90.0 and perfil[-1] == 140.0
