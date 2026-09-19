"""Grava na base quais quitações são contrato antigo registrado tarde."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain.late_registration import Settlement, flag_late_registrations
from app.models.transaction import Transaction

UPDATE_CHUNK = 10_000
STREET_CHUNK = 1_000


@dataclass(frozen=True)
class LateMarking:
    """Resultado de um recálculo, sobre as linhas que ele leu."""

    before: int
    after: int
    by_confidence: dict[str, int]

    @property
    def change_ratio(self) -> float | None:
        if not self.before:
            return None
        return (self.after - self.before) / self.before


def mark_late_registrations(
    db: Session, city: str, streets: Collection[str] | None = None
) -> LateMarking:
    """Recalcula a marca e diz quantas quitações estavam e ficaram marcadas.

    A marca de uma quitação depende das outras do prédio — uma quitação nova do
    lançamento muda a mediana —, então o recálculo é por rua inteira: `streets`
    (valores de `street_search`) limita o trabalho às ruas que uma ingestão
    tocou; sem ele, a cidade inteira é recalculada.
    """
    coverage_start = db.scalar(
        select(func.min(Transaction.settlement_date)).where(Transaction.city == city)
    )
    if coverage_start is None:
        return LateMarking(before=0, after=0, by_confidence={})

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
        Transaction.late_registration_confidence,
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

    # Só escreve o que mudou: numa reingestão quase nada muda. As duas colunas
    # entram na comparação porque linha marcada antes da confiança existir tem
    # a marca sem a confiança.
    by_new_value: dict[str | None, list[int]] = {}
    for r in rows:
        new = flagged.get(r.id)
        if (new, new is not None) != (r.late_registration_confidence, r.late_registration):
            by_new_value.setdefault(new, []).append(r.id)
    for confidence, ids in by_new_value.items():
        for start in range(0, len(ids), UPDATE_CHUNK):
            db.execute(
                update(Transaction)
                .where(Transaction.id.in_(ids[start : start + UPDATE_CHUNK]))
                .values(
                    late_registration=confidence is not None,
                    late_registration_confidence=confidence,
                )
            )
    db.commit()
    return LateMarking(
        before=sum(1 for r in rows if r.late_registration),
        after=len(flagged),
        by_confidence=dict(Counter(flagged.values())),
    )
