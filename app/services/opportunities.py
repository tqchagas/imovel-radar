"""Materialize listing opportunities from ITBI references."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domain.market_stats import Sale
from app.domain.opportunities import (
    MIN_CONFIDENCE,
    MIN_DISCOUNT_PCT,
    RESIDENTIAL_OCCUPATION,
    ListingInput,
    Opportunity,
    address_key,
    compute_opportunity,
    is_alert_eligible,
    window_bounds,
)
from app.models.market_comparable import MarketComparable
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

OPPORTUNITY_COLUMNS = (
    "preco_estimado",
    "desconto_pct",
    "desconto_reais",
    "tipo_referencia",
    "amostra_count",
    "referencia_data_inicio",
    "referencia_data_fim",
    "confianca",
    "oportunidade_motivo",
    "oportunidade_fingerprint",
)


def _valid_residential(stmt: Select, city_key: str) -> Select:
    return stmt.where(
        Transaction.city == city_key,
        func.upper(Transaction.occupation_type) == RESIDENTIAL_OCCUPATION,
        Transaction.declared_value > 0,
        Transaction.built_area_acquired > 0,
    )


def latest_reference_date(db: Session, city: str) -> date | None:
    """Latest settlement date of a usable residential ITBI row in the city."""
    city_key = address_key(city)
    if city_key is None:
        return None
    return db.scalar(
        _valid_residential(select(func.max(Transaction.settlement_date)), city_key)
    )


def fetch_reference_sales(db: Session, city: str, start: date, end: date) -> list[Sale]:
    """Usable residential ITBI rows of the city inside the inclusive window."""
    city_key = address_key(city)
    if city_key is None:
        return []
    stmt = _valid_residential(select(*SALE_COLUMNS), city_key).where(
        Transaction.settlement_date >= start,
        Transaction.settlement_date <= end,
    )
    return [
        Sale(
            neighborhood=row.neighborhood,
            street=row.street,
            street_number=row.street_number,
            settlement_date=row.settlement_date,
            declared_value=float(row.declared_value),
            built_area_acquired=float(row.built_area_acquired),
            construction_type=row.construction_type,
            occupation_type=row.occupation_type,
        )
        for row in db.execute(stmt)
    ]


def _as_float(value) -> float | None:
    return float(value) if value is not None else None


def _listing_input(listing: MarketComparable) -> ListingInput:
    return ListingInput(
        source=listing.source,
        listing_id=listing.listing_id,
        tipo_imovel=listing.tipo_imovel,
        area_util_m2=_as_float(listing.area_util_m2),
        preco_total=_as_float(listing.preco_total),
        bairro=listing.bairro_normalizado or listing.bairro,
        rua=listing.rua_normalizada or listing.rua,
        numero=listing.numero_normalizado or listing.numero,
    )


def _clear(listing: MarketComparable) -> None:
    for column in OPPORTUNITY_COLUMNS:
        setattr(listing, column, None)


def _materialize(
    listing: MarketComparable,
    opportunity: Opportunity,
    *,
    min_discount_pct: float,
    min_confianca: str,
) -> bool:
    listing.preco_estimado = opportunity.preco_estimado
    listing.desconto_pct = opportunity.desconto_pct
    listing.desconto_reais = opportunity.desconto_reais
    listing.tipo_referencia = opportunity.tipo_referencia
    listing.amostra_count = opportunity.amostra_count
    listing.referencia_data_inicio = opportunity.referencia_data_inicio
    listing.referencia_data_fim = opportunity.referencia_data_fim
    listing.confianca = opportunity.confianca
    listing.oportunidade_motivo = "\n".join(opportunity.motivos)
    eligible = is_alert_eligible(
        opportunity, min_discount_pct=min_discount_pct, min_confianca=min_confianca
    )
    # Only alertable opportunities get a fingerprint: it is the notification baseline.
    listing.oportunidade_fingerprint = opportunity.fingerprint if eligible else None
    return eligible


def _active_listings(db: Session, city_key: str, source: str | None) -> list[MarketComparable]:
    stmt = (
        select(MarketComparable)
        .where(
            MarketComparable.cidade_normalizada == city_key,
            MarketComparable.ativo.is_(True),
        )
        .order_by(MarketComparable.id)
    )
    if source:
        stmt = stmt.where(MarketComparable.source == source)
    return list(db.scalars(stmt))


def refresh_opportunities(
    db: Session,
    *,
    city: str,
    source: str | None = None,
    min_discount_pct: float = MIN_DISCOUNT_PCT,
    min_confianca: str = MIN_CONFIDENCE,
    commit: bool = True,
) -> dict:
    """Recalculate and persist the opportunity fields of every active listing."""
    city_key = address_key(city)
    summary = {
        "city": city_key,
        "source": source,
        "reference_date": None,
        "listings": 0,
        "calculated": 0,
        "cleared": 0,
        "alta": 0,
        "media": 0,
        "baixa": 0,
        "eligible": 0,
    }
    if city_key is None:
        return summary

    listings = _active_listings(db, city_key, source)
    summary["listings"] = len(listings)
    if not listings:
        if commit:
            db.commit()
        return summary

    reference_day = latest_reference_date(db, city_key)
    summary["reference_date"] = reference_day
    if reference_day is None:
        if commit:
            db.commit()
        return summary

    start, end = window_bounds(reference_day)
    sales = fetch_reference_sales(db, city_key, start, end)

    for listing in listings:
        opportunity = compute_opportunity(_listing_input(listing), sales, reference_day)
        if opportunity is None:
            _clear(listing)
            summary["cleared"] += 1
            continue
        eligible = _materialize(
            listing,
            opportunity,
            min_discount_pct=min_discount_pct,
            min_confianca=min_confianca,
        )
        summary["calculated"] += 1
        summary[opportunity.confianca] += 1
        summary["eligible"] += int(eligible)

    if commit:
        db.commit()
    else:
        db.flush()
    return summary
