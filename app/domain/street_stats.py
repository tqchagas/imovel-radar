"""Street-level market statistics used by the API and SEO pages."""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from app.domain.market_stats import Sale, price_per_m2, shift_months


@dataclass(frozen=True)
class StreetAddressStat:
    street_number: str
    transaction_count: int
    median_price_per_m2: float | None
    last_settlement_date: date


@dataclass(frozen=True)
class StreetDetail:
    street: str
    transaction_count: int
    property_count: int
    median_ticket: float | None
    p25_ticket: float | None
    p75_ticket: float | None
    median_area: float | None
    median_price_per_m2: float | None
    top_addresses: list[StreetAddressStat]


def _percentile(values: Sequence[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * pct
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def street_detail(
    sales: Sequence[Sale],
    street: str,
    reference: date,
    months: int = 12,
    top_addresses: int = 10,
) -> StreetDetail:
    """Summarize one street over the requested window."""
    window_start = shift_months(reference, months)
    current = [
        sale
        for sale in sales
        if sale.street == street and window_start < sale.settlement_date <= reference
    ]
    tickets = [sale.declared_value for sale in current]
    areas = [
        sale.built_area_acquired
        for sale in current
        if sale.built_area_acquired is not None and sale.built_area_acquired > 0
    ]
    m2_values = [
        value
        for sale in current
        if (value := price_per_m2(sale)) is not None
    ]

    grouped: dict[str, list[Sale]] = defaultdict(list)
    for sale in current:
        if sale.street_number:
            grouped[sale.street_number].append(sale)

    addresses = [
        StreetAddressStat(
            street_number=number,
            transaction_count=len(group),
            median_price_per_m2=statistics.median(
                [m2 for m2 in (price_per_m2(sale) for sale in group) if m2 is not None]
            )
            if any(price_per_m2(sale) is not None for sale in group)
            else None,
            last_settlement_date=max(sale.settlement_date for sale in group),
        )
        for number, group in grouped.items()
    ]
    addresses.sort(key=lambda item: (item.transaction_count, item.last_settlement_date), reverse=True)

    return StreetDetail(
        street=street,
        transaction_count=len(current),
        property_count=len(grouped),
        median_ticket=statistics.median(tickets) if tickets else None,
        p25_ticket=_percentile(tickets, 0.25),
        p75_ticket=_percentile(tickets, 0.75),
        median_area=statistics.median(areas) if areas else None,
        median_price_per_m2=statistics.median(m2_values) if m2_values else None,
        top_addresses=addresses[:top_addresses],
    )
