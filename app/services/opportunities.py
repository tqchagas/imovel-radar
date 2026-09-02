"""Materialize listing opportunities from ITBI references."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.http_client import PortalBlocked
from app.domain.market_stats import Sale
from app.domain.opportunities import (
    MIN_CALIBRATION_LISTINGS,
    MIN_CALIBRATION_SALES,
    MIN_CONFIDENCE,
    MIN_DISCOUNT_PCT,
    MIN_SCORE,
    RESIDENTIAL_OCCUPATION,
    ListingInput,
    Opportunity,
    PriceSuggestion,
    SaleIndex,
    address_key,
    build_calibration,
    compute_opportunity,
    is_alert_eligible,
    window_bounds,
)
from app.models.market_comparable import MarketComparable
from app.models.transaction import Transaction

# One QuintoAndar call per listing, so only listings that would already raise an
# alert on the ITBI reference are worth asking about, and only a bounded number
# of them per run.
QPRECO_SOURCE = "quintoandar"
QPRECO_FETCH_LIMIT = 50
# Consecutive failures that read as "the portal stopped answering us" rather
# than as one bad listing.
QPRECO_MAX_CONSECUTIVE_FAILURES = 3
# The portal re-estimates slowly; a month-old suggestion is still the same
# reading of the same unit.
QPRECO_TTL_DAYS = 30

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
    "nota",
    "nota_itbi",
    "nota_qpreco",
    "qpreco_desconto_pct",
    "dispersao_relativa",
    "fator_calibracao",
    "unidade_fingerprint",
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


def _price_suggestion(listing: MarketComparable) -> PriceSuggestion | None:
    preco = _as_float(listing.price_suggestion_price)
    if preco is None or preco <= 0:
        return None
    return PriceSuggestion(
        preco_sugerido=preco,
        limite_inferior=_as_float(listing.price_suggestion_lower_bound),
        limite_superior=_as_float(listing.price_suggestion_upper_bound),
    )


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
        qpreco=_price_suggestion(listing),
        area_origem=listing.area_origem,
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
    min_nota: int,
) -> bool:
    listing.preco_estimado = opportunity.preco_estimado
    listing.desconto_pct = opportunity.desconto_pct
    listing.desconto_reais = opportunity.desconto_reais
    listing.tipo_referencia = opportunity.tipo_referencia
    listing.amostra_count = opportunity.amostra_count
    listing.referencia_data_inicio = opportunity.referencia_data_inicio
    listing.referencia_data_fim = opportunity.referencia_data_fim
    listing.confianca = opportunity.confianca
    listing.nota = opportunity.nota
    listing.nota_itbi = opportunity.nota_itbi
    listing.nota_qpreco = opportunity.nota_qpreco
    listing.qpreco_desconto_pct = opportunity.qpreco_desconto_pct
    listing.dispersao_relativa = opportunity.dispersao_relativa
    listing.fator_calibracao = opportunity.fator_calibracao
    listing.unidade_fingerprint = opportunity.unidade_fingerprint
    listing.oportunidade_motivo = "\n".join(opportunity.motivos)
    eligible = is_alert_eligible(
        opportunity,
        min_discount_pct=min_discount_pct,
        min_confianca=min_confianca,
        min_nota=min_nota,
    )
    # Only alertable opportunities get a fingerprint: it is the notification baseline.
    listing.oportunidade_fingerprint = opportunity.fingerprint if eligible else None
    return eligible


def _suppress_duplicate_units(
    listings: list[MarketComparable],
    eligible_units: dict[int, str | None],
    best_of_unit: dict[str, tuple[float, int]],
) -> int:
    """Drop the alert baseline of every listing that repeats a unit already won
    by a deeper discount. The opportunity itself stays on the row - only the
    fingerprint goes, and that is what the notification job reads."""
    suppressed = 0
    for listing in listings:
        unit = eligible_units.get(listing.id)
        if unit is None:
            continue
        winner = best_of_unit.get(unit)
        if winner is not None and winner[1] != listing.id:
            listing.oportunidade_fingerprint = None
            suppressed += 1
    return suppressed


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


def _naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def _qpreco_is_stale(listing: MarketComparable, now: datetime, ttl_days: int) -> bool:
    """True when the stored suggestion is missing or old enough to ask again."""
    updated_at = _naive(listing.price_suggestion_updated_at)
    if updated_at is None:
        return True
    return updated_at < _naive(now) - timedelta(days=ttl_days)


def _fetch_qpreco(
    listings: list[MarketComparable],
    opportunities: dict[int, Opportunity | None],
    *,
    fetcher: Callable[[MarketComparable], bool],
    limit: int,
    ttl_days: int,
    now: datetime,
    min_discount_pct: float,
    min_confianca: str,
    min_nota: int,
) -> tuple[list[MarketComparable], int, str | None]:
    """Ask QuintoAndar about the listings whose ITBI reading already alerts.

    The suggestion can only lower a score, so a listing that does not clear the
    alert floor on the ITBI alone can never reach it with a second reference -
    and asking about it would spend a request to change nothing.
    """
    candidates = [
        listing
        for listing in listings
        if listing.source == QPRECO_SOURCE
        and (listing.listing_id or "").strip()
        and is_alert_eligible(
            opportunities.get(listing.id),
            min_discount_pct=min_discount_pct,
            min_confianca=min_confianca,
            min_nota=min_nota,
        )
        and _qpreco_is_stale(listing, now, ttl_days)
    ]
    candidates.sort(key=lambda row: (-(opportunities[row.id].nota), row.id))

    updated: list[MarketComparable] = []
    failed = 0
    consecutive = 0
    stopped: str | None = None
    for listing in candidates[: max(0, limit)]:
        try:
            fetcher(listing)
        except PortalBlocked:
            # Being refused is the portal saying stop. Draining the budget
            # against it is what turns a throttle into a block.
            failed += 1
            stopped = "bloqueado"
            break
        except Exception:  # noqa: BLE001 - one bad listing must not stop the run
            failed += 1
            consecutive += 1
            if consecutive >= QPRECO_MAX_CONSECUTIVE_FAILURES:
                stopped = "falhas_seguidas"
                break
            continue
        consecutive = 0
        updated.append(listing)
    return updated, failed, stopped


def refresh_opportunities(
    db: Session,
    *,
    city: str,
    source: str | None = None,
    min_discount_pct: float = MIN_DISCOUNT_PCT,
    min_confianca: str = MIN_CONFIDENCE,
    min_nota: int = MIN_SCORE,
    min_calibration_listings: int = MIN_CALIBRATION_LISTINGS,
    min_calibration_sales: int = MIN_CALIBRATION_SALES,
    qpreco_fetcher: Callable[[MarketComparable], bool] | None = None,
    qpreco_limit: int = QPRECO_FETCH_LIMIT,
    qpreco_ttl_days: int = QPRECO_TTL_DAYS,
    now: datetime | None = None,
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
        "duplicates": 0,
        "qpreco_buscados": 0,
        "qpreco_falhas": 0,
        "qpreco_interrompido": None,
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

    inputs = {listing.id: _listing_input(listing) for listing in listings}
    index = SaleIndex.build(sales, reference_day)
    calibration = build_calibration(
        inputs.values(),
        index,
        min_listings=min_calibration_listings,
        min_sales=min_calibration_sales,
    )

    # A unit advertised by several agencies, or carried by more than one
    # portal, is one opportunity. Keep the deepest discount and let the rest
    # be calculated but never alerted.
    best_of_unit: dict[str, tuple[float, int]] = {}
    eligible_units: dict[int, str | None] = {}

    opportunities: dict[int, Opportunity | None] = {
        listing.id: compute_opportunity(inputs[listing.id], index, reference_day, calibration)
        for listing in listings
    }

    # Second reference: QuintoAndar's own estimate, fetched only for the
    # listings the ITBI already flags and rescored in the same run.
    if qpreco_fetcher is not None:
        updated, failed, stopped = _fetch_qpreco(
            listings,
            opportunities,
            fetcher=qpreco_fetcher,
            limit=qpreco_limit,
            ttl_days=qpreco_ttl_days,
            now=now or datetime.now(timezone.utc),
            min_discount_pct=min_discount_pct,
            min_confianca=min_confianca,
            min_nota=min_nota,
        )
        summary["qpreco_buscados"] = len(updated)
        summary["qpreco_falhas"] = failed
        summary["qpreco_interrompido"] = stopped
        for listing in updated:
            inputs[listing.id] = _listing_input(listing)
            opportunities[listing.id] = compute_opportunity(
                inputs[listing.id], index, reference_day, calibration
            )

    for listing in listings:
        opportunity = opportunities[listing.id]
        if opportunity is None:
            _clear(listing)
            summary["cleared"] += 1
            continue
        eligible = _materialize(
            listing,
            opportunity,
            min_discount_pct=min_discount_pct,
            min_confianca=min_confianca,
            min_nota=min_nota,
        )
        summary["calculated"] += 1
        summary[opportunity.confianca] += 1
        if eligible:
            unit = opportunity.unidade_fingerprint
            eligible_units[listing.id] = unit
            if unit is not None:
                current = best_of_unit.get(unit)
                if current is None or opportunity.desconto_pct > current[0]:
                    best_of_unit[unit] = (opportunity.desconto_pct, listing.id)

    duplicates = _suppress_duplicate_units(listings, eligible_units, best_of_unit)
    summary["duplicates"] = duplicates
    summary["eligible"] = len(eligible_units) - duplicates

    if commit:
        db.commit()
    else:
        db.flush()
    return summary
