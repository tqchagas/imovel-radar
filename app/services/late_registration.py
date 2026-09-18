"""Grava na base quais quitações são contrato antigo registrado tarde."""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain.late_registration import Settlement, flag_late_registrations
from app.models.transaction import Transaction

UPDATE_CHUNK = 10_000
STREET_CHUNK = 1_000


def mark_late_registrations(
    db: Session, city: str, streets: Collection[str] | None = None
) -> int:
    """Recalcula a marca e devolve quantas quitações ficaram marcadas.

    A marca de uma quitação depende das outras do prédio — uma quitação nova do
    lançamento muda a mediana —, então o recálculo é por rua inteira: `streets`
    (valores de `street_search`) limita o trabalho às ruas que uma ingestão
    tocou; sem ele, a cidade inteira é recalculada.
    """
    coverage_start = db.scalar(
        select(func.min(Transaction.settlement_date)).where(Transaction.city == city)
    )
    if coverage_start is None:
        return 0

    stmt = select(
        Transaction.id,
        Transaction.street,
        Transaction.street_number,
        Transaction.complement,
        Transaction.settlement_date,
        Transaction.declared_value,
        Transaction.calc_base_value,
        Transaction.built_area_acquired,
        Transaction.construction_year,
        Transaction.construction_type,
        Transaction.late_registration,
    ).where(
        Transaction.city == city,
        Transaction.street_number.is_not(None),
        Transaction.complement.is_not(None),
    )
    if streets is None:
        rows = db.execute(stmt).all()
    else:
        wanted = sorted(set(streets))
        rows = []
        for start in range(0, len(wanted), STREET_CHUNK):
            rows.extend(
                db.execute(
                    stmt.where(Transaction.street_search.in_(wanted[start : start + STREET_CHUNK]))
                ).all()
            )

    flagged = flag_late_registrations(
        (
            Settlement(
                id=r.id,
                street=r.street,
                street_number=r.street_number,
                complement=r.complement,
                settlement_date=r.settlement_date,
                declared_value=float(r.declared_value),
                calc_base_value=float(r.calc_base_value),
                built_area_acquired=(
                    float(r.built_area_acquired) if r.built_area_acquired is not None else None
                ),
                construction_year=r.construction_year,
                construction_type=r.construction_type,
            )
            for r in rows
        ),
        coverage_start=coverage_start,
    )

    # Só escreve o que mudou: numa reingestão quase nada muda.
    changes = {
        r.id: (r.id in flagged) for r in rows if bool(r.late_registration) != (r.id in flagged)
    }
    for value in (True, False):
        ids = [i for i, v in changes.items() if v is value]
        for start in range(0, len(ids), UPDATE_CHUNK):
            db.execute(
                update(Transaction)
                .where(Transaction.id.in_(ids[start : start + UPDATE_CHUNK]))
                .values(late_registration=value)
            )
    db.commit()
    return len(flagged)
