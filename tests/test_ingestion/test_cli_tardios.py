"""`marcar-tardios` avisa o scheduler quando o total de marcas salta."""

import json

import pytest
from typer.testing import CliRunner

from app.ingestion import cli
from app.services.late_registration import LateMarking


@pytest.fixture()
def resultado(monkeypatch):
    def usar(marcacao: LateMarking) -> None:
        monkeypatch.setattr(cli, "SessionLocal", lambda: type("Db", (), {"close": lambda self: None})())
        monkeypatch.setattr(cli, "mark_late_registrations", lambda db, cidade: marcacao)

    return usar


def test_ciclo_normal_sai_com_zero(resultado) -> None:
    resultado(LateMarking(before=1000, after=1050, by_confidence={"alta": 600, "media": 450}))

    saida = CliRunner().invoke(cli.app, ["marcar-tardios"])

    assert saida.exit_code == 0
    assert json.loads(saida.stdout)["variacao_pct"] == 5.0


def test_salto_de_mais_de_vinte_por_cento_sai_com_codigo_de_alerta(resultado) -> None:
    resultado(LateMarking(before=1000, after=700, by_confidence={"alta": 700}))

    saida = CliRunner().invoke(cli.app, ["marcar-tardios"])

    assert saida.exit_code == cli.TARDIOS_ALERT_EXIT_CODE
    assert "ALERTA" in saida.output


def test_primeira_marcacao_nao_alerta(resultado) -> None:
    resultado(LateMarking(before=0, after=8000, by_confidence={"media": 8000}))

    assert CliRunner().invoke(cli.app, ["marcar-tardios"]).exit_code == 0
