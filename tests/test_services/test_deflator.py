"""O deflator vem do banco uma vez e fica em memória — é dado que muda por mês."""

from datetime import date

import pytest

from app.models.monetary_index import SERIE_IPCA, MonetaryIndex
from app.services import deflator as servico


def _semear(db_session):
    db_session.add_all(
        [
            MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 1, 1), variacao_pct=0.0),
            MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 2, 1), variacao_pct=10.0),
        ]
    )
    db_session.commit()


def test_monta_o_deflator_do_que_esta_gravado(db_session):
    servico.invalidar_cache()
    _semear(db_session)
    d = servico.carregar_deflator(db_session)
    assert d.referencia == date(2024, 2, 1)
    assert d.fator(date(2024, 1, 1)) == pytest.approx(1.1)


def test_sem_serie_gravada_devolve_none(db_session):
    servico.invalidar_cache()
    # Antes do primeiro `make ipca` a tabela está vazia: a tela mostra só o
    # nominal em vez de quebrar.
    assert servico.carregar_deflator(db_session) is None


def test_a_segunda_chamada_nao_consulta_o_banco_de_novo(db_session):
    servico.invalidar_cache()
    _semear(db_session)
    primeiro = servico.carregar_deflator(db_session)
    db_session.add(
        MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 3, 1), variacao_pct=10.0)
    )
    db_session.commit()
    assert servico.carregar_deflator(db_session) is primeiro


def test_invalidar_cache_faz_reler(db_session):
    servico.invalidar_cache()
    _semear(db_session)
    servico.carregar_deflator(db_session)
    db_session.add(
        MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 3, 1), variacao_pct=10.0)
    )
    db_session.commit()
    servico.invalidar_cache()
    assert servico.carregar_deflator(db_session).referencia == date(2024, 3, 1)
