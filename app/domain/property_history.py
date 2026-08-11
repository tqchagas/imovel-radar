"""Build property-level history, timeline markers, and summary cards."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from app.domain.complement import normalize_complement, normalize_street_key
from app.models.transaction import Transaction

# Fraction relative to the max ideal fraction seen for this unit.
# BH stores condo ideal fraction (e.g. 0.003), not ownership % of the unit.
FULL_FRACTION_RATIO = 0.90
AREA_DIVERGENCE_RATIO = 0.20


@dataclass(frozen=True)
class PropertyKey:
    city: str
    street: str
    street_number: str | None
    complement: str | None  # raw display value from entry (may be None)


@dataclass
class TimelinePoint:
    transaction_id: int
    settlement_date: date
    declared_value: float
    calc_base_value: float
    calc_base_gap_pct: float | None
    built_area_acquired: float | None
    price_per_m2: float | None
    acquired_fraction: float | None
    is_partial: bool
    area_divergent: bool
    markers: list[str]


@dataclass
class PropertySummary:
    last_sale_date: date | None
    last_sale_value: float | None
    appreciation_pct: float | None
    last_price_per_m2: float | None
    price_per_m2_delta_pct: float | None
    transaction_count: int
    year_from: int | None
    year_to: int | None


def complements_match(a: str | None, b: str | None) -> bool:
    return normalize_complement(a) == normalize_complement(b)


def transaction_matches_key(tx: Transaction, key: PropertyKey) -> bool:
    if tx.city != key.city:
        return False
    if normalize_street_key(tx.street) != normalize_street_key(key.street):
        return False
    if normalize_street_key(tx.street_number) != normalize_street_key(key.street_number):
        return False
    if key.complement is None or normalize_complement(key.complement) is None:
        # Lot/number page: only rows without a meaningful complement
        return normalize_complement(tx.complement) is None
    return complements_match(tx.complement, key.complement)


def filter_transactions_for_key(
    candidates: Sequence[Transaction], key: PropertyKey
) -> list[Transaction]:
    matched = [tx for tx in candidates if transaction_matches_key(tx, key)]
    return sorted(matched, key=lambda t: (t.settlement_date, t.id))


def _f(value: object | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _price_per_m2(declared: float, area: float | None) -> float | None:
    if area is None or area <= 0:
        return None
    return declared / area


def _gap_pct(declared: float, calc_base: float) -> float | None:
    if declared <= 0:
        return None
    return ((calc_base - declared) / declared) * 100.0


def _reference_fraction(transactions: Sequence[Transaction]) -> float | None:
    fractions = [
        f for f in (_f(t.acquired_fraction) for t in transactions) if f is not None
    ]
    if not fractions:
        return None
    return max(fractions)


def _is_partial(tx: Transaction, ref_fraction: float | None) -> bool:
    frac = _f(tx.acquired_fraction)
    if frac is None or ref_fraction is None or ref_fraction <= 0:
        return False
    return frac < FULL_FRACTION_RATIO * ref_fraction


def _reference_area(full_sales: Sequence[Transaction]) -> float | None:
    areas = [
        a
        for a in (_f(t.built_area_acquired) for t in full_sales)
        if a is not None and a > 0
    ]
    if not areas:
        return None
    return statistics.median(areas)


def _area_divergent(tx: Transaction, ref_area: float | None) -> bool:
    area = _f(tx.built_area_acquired)
    if area is None or ref_area is None or ref_area <= 0:
        return False
    return abs(area - ref_area) / ref_area > AREA_DIVERGENCE_RATIO


def build_timeline(transactions: Sequence[Transaction]) -> list[TimelinePoint]:
    """Chronological timeline points with honesty markers."""
    ordered = sorted(transactions, key=lambda t: (t.settlement_date, t.id))
    ref_fraction = _reference_fraction(ordered)
    full = [t for t in ordered if not _is_partial(t, ref_fraction)]
    ref_area = _reference_area(full if full else ordered)

    points: list[TimelinePoint] = []
    for tx in ordered:
        declared = float(tx.declared_value)
        calc_base = float(tx.calc_base_value)
        area = _f(tx.built_area_acquired)
        partial = _is_partial(tx, ref_fraction)
        divergent = _area_divergent(tx, ref_area)
        markers: list[str] = []
        if partial:
            markers.append("cota_parcial")
        if divergent:
            markers.append("area_divergente")
        gap = _gap_pct(declared, calc_base)
        if gap is not None and abs(gap) >= 1.0:
            markers.append("base_divergente")

        points.append(
            TimelinePoint(
                transaction_id=tx.id,
                settlement_date=tx.settlement_date,
                declared_value=declared,
                calc_base_value=calc_base,
                calc_base_gap_pct=gap,
                built_area_acquired=area,
                price_per_m2=_price_per_m2(declared, area),
                acquired_fraction=_f(tx.acquired_fraction),
                is_partial=partial,
                area_divergent=divergent,
                markers=markers,
            )
        )
    return points


def build_summary(transactions: Sequence[Transaction]) -> PropertySummary:
    ordered = sorted(transactions, key=lambda t: (t.settlement_date, t.id))
    if not ordered:
        return PropertySummary(
            last_sale_date=None,
            last_sale_value=None,
            appreciation_pct=None,
            last_price_per_m2=None,
            price_per_m2_delta_pct=None,
            transaction_count=0,
            year_from=None,
            year_to=None,
        )

    last = ordered[-1]
    last_area = _f(last.built_area_acquired)
    last_value = float(last.declared_value)

    ref_fraction = _reference_fraction(ordered)
    full_sales = [t for t in ordered if not _is_partial(t, ref_fraction)]

    appreciation_pct: float | None = None
    if len(full_sales) >= 2:
        prev, curr = full_sales[-2], full_sales[-1]
        prev_v = float(prev.declared_value)
        curr_v = float(curr.declared_value)
        if prev_v > 0:
            appreciation_pct = ((curr_v - prev_v) / prev_v) * 100.0

    # Secondary: Δ R$/m² across last two events that have area (any fraction).
    with_m2 = [
        t
        for t in ordered
        if (a := _f(t.built_area_acquired)) is not None
        and a > 0
        and float(t.declared_value) > 0
    ]
    price_per_m2_delta_pct: float | None = None
    if len(with_m2) >= 2:
        prev, curr = with_m2[-2], with_m2[-1]
        prev_m2 = _price_per_m2(float(prev.declared_value), _f(prev.built_area_acquired))
        curr_m2 = _price_per_m2(float(curr.declared_value), _f(curr.built_area_acquired))
        if prev_m2 and curr_m2 and prev_m2 > 0:
            price_per_m2_delta_pct = ((curr_m2 - prev_m2) / prev_m2) * 100.0

    return PropertySummary(
        last_sale_date=last.settlement_date,
        last_sale_value=last_value,
        appreciation_pct=appreciation_pct,
        last_price_per_m2=_price_per_m2(last_value, last_area),
        price_per_m2_delta_pct=price_per_m2_delta_pct,
        transaction_count=len(ordered),
        year_from=ordered[0].settlement_date.year,
        year_to=ordered[-1].settlement_date.year,
    )


def key_from_transaction(tx: Transaction) -> PropertyKey:
    return PropertyKey(
        city=tx.city,
        street=tx.street,
        street_number=tx.street_number,
        complement=tx.complement,
    )
