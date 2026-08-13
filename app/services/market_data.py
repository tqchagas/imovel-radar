"""Shared market-data queries for API responses and rendered pages."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domain.market_stats import Sale, shift_months
from app.models.transaction import Transaction

SALE_COLUMNS = (
    Transaction.neighborhood,
    Transaction.street,
    Transaction.street_number,
    Transaction.settlement_date,
    Transaction.declared_value,
    Transaction.built_area_acquired,
    Transaction.construction_type,
    Transaction.occupation_type,
)


def scoped(stmt: Select, city: str | None) -> Select:
    return stmt.where(Transaction.city == city) if city else stmt


def reference_date(db: Session, city: str | None) -> date | None:
    return db.scalar(scoped(select(func.max(Transaction.settlement_date)), city))


def fetch_sales(
    db: Session,
    city: str | None,
    start: date,
    end: date,
    neighborhood: str | None = None,
    street: str | None = None,
) -> list[Sale]:
    stmt = scoped(select(*SALE_COLUMNS), city).where(
        Transaction.settlement_date > start,
        Transaction.settlement_date <= end,
    )
    if neighborhood:
        stmt = stmt.where(Transaction.neighborhood == neighborhood)
    if street:
        stmt = stmt.where(Transaction.street == street)

    return [
        Sale(
            neighborhood=row.neighborhood,
            street=row.street,
            street_number=row.street_number,
            settlement_date=row.settlement_date,
            declared_value=float(row.declared_value),
            built_area_acquired=(
                float(row.built_area_acquired)
                if row.built_area_acquired is not None
                else None
            ),
            construction_type=row.construction_type,
            occupation_type=row.occupation_type,
        )
        for row in db.execute(stmt)
    ]


def fetch_window_sales(
    db: Session,
    city: str | None,
    months: int,
    neighborhood: str | None = None,
    street: str | None = None,
) -> tuple[date | None, list[Sale]]:
    reference = reference_date(db, city)
    if reference is None:
        return None, []
    return reference, fetch_sales(
        db,
        city,
        shift_months(reference, months * 2),
        reference,
        neighborhood=neighborhood,
        street=street,
    )
