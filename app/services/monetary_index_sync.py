"""Põe a série do índice no banco, reconciliando com o que já está lá.

Sem `on_conflict_do_update` de propósito: ele é exclusivo do dialeto Postgres e
os testes rodam em SQLite. A série inteira tem ~223 linhas, então ler o que
existe e decidir em Python custa nada e roda nos dois bancos.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.bcb_sgs import CODIGO_IPCA, IndexPoint, fetch_series
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex


def save_points(
    db: Session, series: str, points: Iterable[IndexPoint]
) -> tuple[int, int]:
    """Grava os pontos e devolve `(inseridos, atualizados)`."""
    existentes = {
        linha.competencia: linha
        for linha in db.scalars(
            select(MonetaryIndex).where(MonetaryIndex.series == series)
        )
    }

    inseridos = atualizados = 0
    for ponto in points:
        linha = existentes.get(ponto.competencia)
        if linha is None:
            db.add(
                MonetaryIndex(
                    series=series,
                    competencia=ponto.competencia,
                    variacao_pct=ponto.variacao_pct,
                )
            )
            inseridos += 1
        elif float(linha.variacao_pct) != ponto.variacao_pct:
            linha.variacao_pct = ponto.variacao_pct
            atualizados += 1
    db.commit()
    return inseridos, atualizados


def sync_ipca(db: Session, desde: date = date(2008, 1, 1)) -> tuple[int, int]:
    pontos = fetch_series(codigo=CODIGO_IPCA, desde=desde)
    return save_points(db, SERIE_IPCA, pontos)
