from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.complement import normalize_complement, normalize_street_key
from app.domain.property_history import (
    PropertyKey,
    build_summary,
    build_timeline,
    filter_transactions_for_key,
    key_from_transaction,
    streets_match,
)
from app.domain.slugs import stored_city
from app.models.transaction import Transaction
from app.schemas.property import (
    PropertyOut,
    PropertySummaryOut,
    TimelinePointOut,
)
from app.schemas.transaction import TransactionOut

router = APIRouter()


def _fetch_building_candidates(
    db: Session,
    city: str,
    street: str,
    street_number: str | None,
) -> list[Transaction]:
    number_key = normalize_street_key(street_number)
    if number_key == "-":
        number_key = ""

    stmt = select(Transaction).where(Transaction.city == stored_city(city))
    if number_key:
        stmt = stmt.where(
            func.upper(func.trim(Transaction.street_number)) == number_key
        )
    else:
        stmt = stmt.where(
            (Transaction.street_number.is_(None))
            | (func.trim(Transaction.street_number) == "")
        )

    candidates = list(db.scalars(stmt).all())
    return [tx for tx in candidates if streets_match(tx.street, street)]


def _to_property_out(key: PropertyKey, matched: list[Transaction]) -> PropertyOut:
    summary = build_summary(matched)
    timeline = build_timeline(matched)
    # Newest first in the table (timeline stays chronological in builder)
    table_rows = sorted(matched, key=lambda t: (t.settlement_date, t.id), reverse=True)
    sample = table_rows[0]

    return PropertyOut(
        city=sample.city,
        street=sample.street,
        street_number=sample.street_number,
        complement=sample.complement if key.complement else None,
        complement_normalized=normalize_complement(
            sample.complement if key.complement else None
        ),
        summary=PropertySummaryOut(
            last_sale_date=summary.last_sale_date,
            last_sale_value=summary.last_sale_value,
            appreciation_pct=summary.appreciation_pct,
            last_price_per_m2=summary.last_price_per_m2,
            price_per_m2_delta_pct=summary.price_per_m2_delta_pct,
            transaction_count=summary.transaction_count,
            year_from=summary.year_from,
            year_to=summary.year_to,
        ),
        timeline=[
            TimelinePointOut(
                transaction_id=p.transaction_id,
                settlement_date=p.settlement_date,
                declared_value=p.declared_value,
                calc_base_value=p.calc_base_value,
                calc_base_gap_pct=p.calc_base_gap_pct,
                built_area_acquired=p.built_area_acquired,
                price_per_m2=p.price_per_m2,
                acquired_fraction=p.acquired_fraction,
                is_partial=p.is_partial,
                area_divergent=p.area_divergent,
                markers=p.markers,
            )
            for p in timeline
        ],
        transactions=[TransactionOut.model_validate(t) for t in table_rows],
    )


@router.get("/properties", response_model=PropertyOut)
def get_property(
    city: str = Query(...),
    street: str = Query(...),
    street_number: str | None = Query(None),
    complement: str | None = Query(None),
    db: Session = Depends(get_db),
) -> PropertyOut:
    key = PropertyKey(
        city=city,
        street=street,
        street_number=street_number,
        complement=complement if complement not in (None, "") else None,
    )
    candidates = _fetch_building_candidates(db, key.city, key.street, key.street_number)
    matched = filter_transactions_for_key(candidates, key)
    if not matched:
        raise HTTPException(status_code=404, detail="Property not found")
    return _to_property_out(key, matched)


@router.get(
    "/properties/by-transaction/{transaction_id}",
    response_model=PropertyOut,
)
def get_property_by_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
) -> PropertyOut:
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    key = key_from_transaction(tx)
    candidates = _fetch_building_candidates(db, key.city, key.street, key.street_number)
    matched = filter_transactions_for_key(candidates, key)
    if not matched:
        # Should not happen if tx exists and matches itself
        matched = [tx]
    return _to_property_out(key, matched)
