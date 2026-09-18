"""Grava na base quais quitações são contrato antigo registrado tarde."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain.late_registration import Settlement, flag_late_registrations
from app.models.transaction import Transaction

UPDATE_CHUNK = 10_000


def mark_late_registrations(db: Session, city: str) -> int:
    """Recalcula a marca da cidade inteira e devolve quantas ficaram marcadas.

    A marca de uma quitação depende das outras do prédio — uma quitação nova do
    lançamento muda a mediana —, então a cidade é recalculada toda a cada
    ingestão, e não só as linhas novas.
    """
    coverage_start = db.scalar(
        select(func.min(Transaction.settlement_date)).where(Transaction.city == city)
    )
    if coverage_start is None:
        return 0

    rows = db.execute(
        select(
            Transaction.id,
            Transaction.street,
            Transaction.street_number,
            Transaction.complement,
            Transaction.settlement_date,
            Transaction.declared_value,
            Transaction.built_area_acquired,
            Transaction.construction_year,
            Transaction.late_registration,
        ).where(
            Transaction.city == city,
            Transaction.street_number.is_not(None),
            Transaction.complement.is_not(None),
        )
    ).all()
    flagged = flag_late_registrations(
        (
            Settlement(
                id=r.id,
                street=r.street,
                street_number=r.street_number,
                complement=r.complement,
                settlement_date=r.settlement_date,
                declared_value=float(r.declared_value),
                built_area_acquired=(
                    float(r.built_area_acquired) if r.built_area_acquired is not None else None
                ),
                construction_year=r.construction_year,
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
