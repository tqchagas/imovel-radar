"""Reingerir a série tem que atualizar mês revisado, não duplicar nem ignorar."""

from datetime import date

from app.ingestion.bcb_sgs import IndexPoint
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex
from app.services import monetary_index_sync


def test_primeira_carga_insere_tudo(db_session):
    inseridos, atualizados = monetary_index_sync.save_points(
        db_session,
        SERIE_IPCA,
        [
            IndexPoint(date(2024, 1, 1), 0.42),
            IndexPoint(date(2024, 2, 1), 0.83),
        ],
    )
    assert (inseridos, atualizados) == (2, 0)
    assert db_session.query(MonetaryIndex).count() == 2


def test_mes_revisado_pelo_ibge_atualiza_a_linha_existente(db_session):
    # O IBGE revisa mês já publicado e o SGS republica. Ignorar deixaria a base
    # divergindo da fonte para sempre; inserir de novo violaria a chave única.
    monetary_index_sync.save_points(
        db_session, SERIE_IPCA, [IndexPoint(date(2024, 1, 1), 0.42)]
    )
    inseridos, atualizados = monetary_index_sync.save_points(
        db_session, SERIE_IPCA, [IndexPoint(date(2024, 1, 1), 0.45)]
    )
    assert (inseridos, atualizados) == (0, 1)
    gravado = db_session.query(MonetaryIndex).one()
    assert float(gravado.variacao_pct) == 0.45


def test_mes_sem_mudanca_nao_conta_como_atualizado(db_session):
    monetary_index_sync.save_points(
        db_session, SERIE_IPCA, [IndexPoint(date(2024, 1, 1), 0.42)]
    )
    assert monetary_index_sync.save_points(
        db_session, SERIE_IPCA, [IndexPoint(date(2024, 1, 1), 0.42)]
    ) == (0, 0)


def test_sync_ipca_grava_o_que_o_sgs_devolveu(db_session, monkeypatch):
    monkeypatch.setattr(
        monetary_index_sync,
        "fetch_series",
        lambda **kwargs: [IndexPoint(date(2024, 1, 1), 0.42)],
    )
    assert monetary_index_sync.sync_ipca(db_session) == (1, 0)
    assert db_session.query(MonetaryIndex).one().competencia == date(2024, 1, 1)
