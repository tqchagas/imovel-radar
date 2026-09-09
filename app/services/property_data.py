"""Property lookup shared by JSON APIs and server-rendered pages."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.complement import normalize_complement, normalize_street_key
from app.domain.monetary_correction import Deflator, competencia_de
from app.domain.property_history import (
    PropertyKey,
    TimelinePoint,
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
from app.services.deflator import carregar_deflator


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


def _appreciation_real_pct(
    timeline: list[TimelinePoint], deflator: Deflator | None
) -> float | None:
    """Corrige as mesmas duas últimas vendas cheias que `build_summary` usa
    para a nominal, e compara as corrigidas. Usar outro par produziria dois
    números que não respondem à mesma pergunta na mesma tela."""
    if deflator is None:
        return None
    full_points = [p for p in timeline if not p.is_partial]
    if len(full_points) < 2:
        return None
    prev, curr = full_points[-2], full_points[-1]
    prev_corrigido = deflator.corrigir(prev.declared_value, competencia_de(prev.settlement_date))
    curr_corrigido = deflator.corrigir(curr.declared_value, competencia_de(curr.settlement_date))
    if prev_corrigido is None or curr_corrigido is None or prev_corrigido <= 0:
        return None
    return ((curr_corrigido / prev_corrigido) - 1) * 100.0


def to_property_out(
    key: PropertyKey,
    matched: list[Transaction],
    deflator: Deflator | None = None,
) -> PropertyOut:
    summary = build_summary(matched)
    timeline = build_timeline(matched)
    table_rows = sorted(matched, key=lambda t: (t.settlement_date, t.id), reverse=True)
    sample = table_rows[0]

    timeline_out = []
    for point in timeline:
        declared_value_corrected = None
        price_per_m2_corrected = None
        if deflator is not None:
            declared_value_corrected = deflator.corrigir(
                point.declared_value, competencia_de(point.settlement_date)
            )
            if declared_value_corrected is not None and point.built_area_acquired:
                area = point.built_area_acquired
                if area > 0:
                    price_per_m2_corrected = declared_value_corrected / area
        timeline_out.append(
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
                declared_value_corrected=declared_value_corrected,
                price_per_m2_corrected=price_per_m2_corrected,
            )
        )

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
            appreciation_real_pct=_appreciation_real_pct(timeline, deflator),
        ),
        timeline=timeline_out,
        transactions=[TransactionOut.model_validate(t) for t in table_rows],
        correction_reference=deflator.referencia if deflator else None,
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
    return to_property_out(key, matched, carregar_deflator(db)) if matched else None


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
        return to_property_out(key, matched, carregar_deflator(db))
    return None
