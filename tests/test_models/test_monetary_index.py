"""Um mês só pode ter uma variação por série — reingerir não pode duplicar."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.monetary_index import SERIE_IPCA, MonetaryIndex


def test_grava_a_variacao_do_mes(db_session):
    db_session.add(
        MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 8, 1), variacao_pct=-0.02)
    )
    db_session.commit()
    gravado = db_session.query(MonetaryIndex).one()
    assert float(gravado.variacao_pct) == -0.02


def test_o_mesmo_mes_da_mesma_serie_nao_entra_duas_vezes(db_session):
    for _ in range(2):
        db_session.add(
            MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 8, 1), variacao_pct=0.42)
        )
    with pytest.raises(IntegrityError):
        db_session.commit()
