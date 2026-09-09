"""O deflator pronto para as rotas, lido do banco uma vez por hora.

A série muda uma vez por mês e o `Deflator` é imutável, então ler a tabela a
cada request seria uma consulta por página para um dado que não se move. O TTL
existe só para o processo enxergar o `make ipca` do dia sem precisar de deploy.
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.monetary_correction import Deflator
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex

TTL_SEGUNDOS = 3600

_cache: dict[str, tuple[float, Deflator | None]] = {}


def invalidar_cache() -> None:
    _cache.clear()


def carregar_deflator(db: Session, series: str = SERIE_IPCA) -> Deflator | None:
    """O deflator da série, ou `None` enquanto a tabela estiver vazia."""
    agora = time.monotonic()
    guardado = _cache.get(series)
    if guardado is not None and agora - guardado[0] < TTL_SEGUNDOS:
        return guardado[1]

    linhas = list(
        db.scalars(select(MonetaryIndex).where(MonetaryIndex.series == series))
    )
    deflator = Deflator.from_points(linhas) if linhas else None
    _cache[series] = (agora, deflator)
    return deflator
