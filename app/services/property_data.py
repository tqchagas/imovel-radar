"""Property lookup shared by JSON APIs and server-rendered pages."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.complement import normalize_complement, normalize_street_key
from app.domain.property_history import (
    PropertyKey,
    build_summary,
    build_timeline,
    filter_transactions_for_key,
    key_from_transaction,
    streets_match,
)
from app.domain.slugs import slugify, stored_city
from app.models.transaction import Transaction
from app.schemas.property import PropertyOut, PropertySummaryOut, TimelinePointOut
from app.schemas.transaction import TransactionOut


def fetch_building_candidates(
    db: Session, city: str, street: str, street_number: str | None
) -> list[Transaction]:
    number_key = normalize_street_key(street_number)
    if number_key == "-":
        number_key = ""
    stmt = select(Transaction).where(Transaction.city == stored_city(city))
    if number_key:
        stmt = stmt.where(func.upper(func.trim(Transaction.street_number)) == number_key)
    else:
        stmt = stmt.where(
            (Transaction.street_number.is_(None))
            | (func.trim(Transaction.street_number) == "")
        )
    candidates = list(db.scalars(stmt).all())
    return [tx for tx in candidates if streets_match(tx.street, street)]


def to_property_out(key: PropertyKey, matched: list[Transaction]) -> PropertyOut:
    summary = build_summary(matched)
    timeline = build_timeline(matched)
    table_rows = sorted(matched, key=lambda t: (t.settlement_date, t.id), reverse=True)
    sample = table_rows[0]
    return PropertyOut(
        city=sample.city,
        street=sample.street,
        street_number=sample.street_number,
        complement=sample.complement if key.complement else None,
        complement_normalized=normalize_complement(sample.complement if key.complement else None),
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
                transaction_id=point.transaction_id,
                settlement_date=point.settlement_date,
                declared_value=point.declared_value,
                calc_base_value=point.calc_base_value,
                calc_base_gap_pct=point.calc_base_gap_pct,
                built_area_acquired=point.built_area_acquired,
                price_per_m2=point.price_per_m2,
                acquired_fraction=point.acquired_fraction,
                is_partial=point.is_partial,
                area_divergent=point.area_divergent,
                markers=point.markers,
            )
            for point in timeline
        ],
        transactions=[TransactionOut.model_validate(t) for t in table_rows],
    )


def get_property(
    db: Session,
    city: str,
    street: str,
    street_number: str | None,
    complement: str | None,
) -> PropertyOut | None:
    key = PropertyKey(city, street, street_number, complement or None)
    candidates = fetch_building_candidates(db, city, street, street_number)
    matched = filter_transactions_for_key(candidates, key)
    return to_property_out(key, matched) if matched else None


def get_property_from_slugs(
    db: Session,
    city_slug: str,
    street_slug: str,
    street_number: str | None,
    complement_slug: str | None,
) -> PropertyOut | None:
    city = stored_city(city_slug)
    candidates = fetch_building_candidates(db, city, street_slug, street_number)
    for candidate in candidates:
        if slugify(candidate.street) != street_slug:
            continue
        if complement_slug and slugify(candidate.complement or "") != complement_slug:
            continue
        if not complement_slug and candidate.complement:
            continue
        key = key_from_transaction(candidate)
        matched = filter_transactions_for_key(candidates, key)
        return to_property_out(key, matched)
    return None
