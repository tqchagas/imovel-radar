from datetime import date

import pytest

from app.models.registry_address import RegistryAddress
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
