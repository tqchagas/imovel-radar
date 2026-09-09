"""O SGS devolve texto com vírgula decimal trocada por ponto e sinal negativo."""

from datetime import date

import pytest

from app.ingestion import bcb_sgs


def test_le_data_no_formato_brasileiro_e_valor_com_ponto():
    pontos = bcb_sgs.parse_series([{"data": "01/01/2024", "valor": "0.42"}])
    assert pontos == [bcb_sgs.IndexPoint(competencia=date(2024, 1, 1), variacao_pct=0.42)]


def test_deflacao_do_mes_e_negativa():
    # Agosto de 2024 fechou em -0,02%. Perder o sinal inverteria a correção.
    pontos = bcb_sgs.parse_series([{"data": "01/08/2024", "valor": "-0.02"}])
    assert pontos[0].variacao_pct == -0.02


def test_ordena_por_competencia():
    pontos = bcb_sgs.parse_series(
        [{"data": "01/03/2024", "valor": "0.16"}, {"data": "01/01/2024", "valor": "0.42"}]
    )
    assert [p.competencia for p in pontos] == [date(2024, 1, 1), date(2024, 3, 1)]


def test_resposta_de_erro_sobe_em_vez_de_virar_serie_vazia(monkeypatch):
    # Série vazia viraria "sem índice" em silêncio, e a tela pararia de corrigir
    # sem ninguém saber por quê.
    class RespostaRuim:
        status_code = 500

        def raise_for_status(self):
            raise RuntimeError("500")

    monkeypatch.setattr(bcb_sgs.http_client, "request", lambda *a, **k: RespostaRuim())
    with pytest.raises(RuntimeError):
        bcb_sgs.fetch_series()


def test_monta_a_url_com_a_data_inicial_no_formato_do_sgs(monkeypatch):
    capturada = {}

    class Resposta:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"data": "01/01/2008", "valor": "0.54"}]

    def falsa_request(method, url, **kwargs):
        capturada["url"] = url
        return Resposta()

    monkeypatch.setattr(bcb_sgs.http_client, "request", falsa_request)
    pontos = bcb_sgs.fetch_series(desde=date(2008, 1, 1))
    assert "bcdata.sgs.433" in capturada["url"]
    assert "dataInicial=01/01/2008" in capturada["url"]
    assert pontos[0].competencia == date(2008, 1, 1)
