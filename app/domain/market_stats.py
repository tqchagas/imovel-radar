"""Neighborhood-level aggregations over settled ITBI transactions.

Everything here is pure: routes fetch the rows, these functions summarize them.
R$/m² is always declared value over acquired built area — BH's `acquired_fraction`
is the condo ideal fraction, not an ownership share, so it cannot be used to tell
partial sales apart at neighborhood scale (see `property_history`).
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Sequence

CONSTRUCTION_TYPE_LABELS = {
    "AC": "Apartamento comercial",
    "AP": "Apartamento",
    "BA": "Barracão",
    "BC": "Barracão comercial",
    "CA": "Casa",
    "CC": "Casa comercial",
    "GP": "Galpão",
    "LJ": "Loja",
    "LV": "Lote vago",
    "SL": "Sala",
    "VC": "Vaga de garagem comercial",
    "VR": "Vaga de garagem residencial",
    "VV": "Vaga de garagem uso misto",
    # Legacy values retained for already-ingested datasets.
    "CS": "Casa",
    "LO": "Loja / sala comercial",
    "GA": "Garagem",
    "TE": "Terreno",
}

CONSTRUCTION_TYPE_DESCRIPTIONS = {
    "AC": "Imóvel destinado a função diversa de habitação em construção originalmente residencial, incluindo apart-hotel.",
    "AP": "Habitação multifamiliar em edificação vertical, com uma ou mais unidades por pavimento e áreas comuns.",
    "BA": "Construção residencial igual ou menor que 60 m² por unidade.",
    "BC": "Construção comercial igual ou menor que 60 m² por unidade.",
    "CA": "Casa residencial com mais de 60 m² ou construção residencial não enquadrada nos demais tipos.",
    "CC": "Construção comercial com mais de 60 m².",
    "GP": "Construção de um pavimento para fins industriais, depósitos, oficinas ou serviços, com grandes vãos.",
    "LJ": "Imóvel não residencial de rua ou em centro comercial destinado à exposição e venda ou atividades similares.",
    "LV": "Terreno sem nenhum tipo de construção ou edificação.",
    "SL": "Unidade não residencial destinada à prestação de serviços em conjunto vertical com entradas comuns.",
    "VC": "Vaga autônoma de garagem para uso não residencial ou em edifício-garagem.",
    "VR": "Vaga autônoma de garagem para uso residencial.",
    "VV": "Vaga de garagem de uso misto, código legado não utilizado atualmente.",
}


@dataclass(frozen=True)
class Sale:
    """The slice of a transaction the market views need."""

    neighborhood: str
    street: str
    settlement_date: date
    declared_value: float
    built_area_acquired: float | None
    construction_type: str | None
    occupation_type: str | None
    street_number: str | None = None
    # Só o desfecho precisa voltar da venda para a linha que a originou; as
    # visões de mercado agregam e não olham para trás.
    transaction_id: int | None = None


@dataclass
class NeighborhoodStat:
    neighborhood: str
    transaction_count: int
    median_price_per_m2: float | None
    delta_pct: float | None


@dataclass
class TypeStat:
    construction_type: str | None
    label: str
    description: str | None
    transaction_count: int
    median_price_per_m2: float | None


@dataclass
class StreetStat:
    street: str
    transaction_count: int
    median_price_per_m2: float | None


@dataclass
class NeighborhoodDetail:
    neighborhood: str
    transaction_count: int
    residential_share_pct: float | None
    median_price_per_m2: float | None
    delta_pct: float | None
    median_ticket: float | None
    p25_ticket: float | None
    p75_ticket: float | None
    median_area: float | None
    per_month: float | None
    by_construction_type: list[TypeStat]
    top_streets: list[StreetStat]


def shift_months(reference: date, months: int) -> date:
    """Same day-of-month `months` back, clamped to the shorter month."""
    total = reference.year * 12 + (reference.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    day = min(reference.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def price_per_m2(sale: Sale) -> float | None:
    area = sale.built_area_acquired
    if area is None or area <= 0:
        return None
    return sale.declared_value / area


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _percentile(values: Sequence[float], pct: float) -> float | None:
    """Linear-interpolated percentile; `statistics.quantiles` needs 2+ points."""
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


def _median_m2(sales: Sequence[Sale]) -> float | None:
    return _median([m2 for m2 in (price_per_m2(s) for s in sales) if m2 is not None])


def _delta_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return (current / previous - 1) * 100


def in_window(sale: Sale, start: date, end: date) -> bool:
    return start < sale.settlement_date <= end


def neighborhood_ranking(
    sales: Sequence[Sale],
    reference: date,
    months: int = 12,
    limit: int | None = None,
    min_transactions: int = 1,
) -> list[NeighborhoodStat]:
    """Median R$/m² per neighborhood in the window, vs. the window before it."""
    window_start = shift_months(reference, months)
    previous_start = shift_months(reference, months * 2)

    current: dict[str, list[Sale]] = defaultdict(list)
    previous: dict[str, list[Sale]] = defaultdict(list)
    for sale in sales:
        if in_window(sale, window_start, reference):
            current[sale.neighborhood].append(sale)
        elif in_window(sale, previous_start, window_start):
            previous[sale.neighborhood].append(sale)

    stats = [
        NeighborhoodStat(
            neighborhood=name,
            transaction_count=len(group),
            median_price_per_m2=_median_m2(group),
            delta_pct=_delta_pct(_median_m2(group), _median_m2(previous.get(name, []))),
        )
        for name, group in current.items()
        if len(group) >= min_transactions
    ]
    stats.sort(key=lambda s: (s.median_price_per_m2 or 0, s.transaction_count), reverse=True)
    return stats[:limit] if limit else stats


def neighborhood_detail(
    sales: Sequence[Sale],
    neighborhood: str,
    reference: date,
    months: int = 12,
    top_streets: int = 5,
    min_street_transactions: int = 2,
) -> NeighborhoodDetail:
    """Full stat block for one neighborhood: `sales` may span both windows."""
    window_start = shift_months(reference, months)
    previous_start = shift_months(reference, months * 2)

    current = [s for s in sales if in_window(s, window_start, reference)]
    previous = [s for s in sales if in_window(s, previous_start, window_start)]

    tickets = [s.declared_value for s in current]
    areas = [
        s.built_area_acquired
        for s in current
        if s.built_area_acquired is not None and s.built_area_acquired > 0
    ]
    residential = sum(1 for s in current if (s.occupation_type or "") == "RESIDENCIAL")

    return NeighborhoodDetail(
        neighborhood=neighborhood,
        transaction_count=len(current),
        residential_share_pct=(residential / len(current) * 100) if current else None,
        median_price_per_m2=_median_m2(current),
        delta_pct=_delta_pct(_median_m2(current), _median_m2(previous)),
        median_ticket=_median(tickets),
        p25_ticket=_percentile(tickets, 0.25),
        p75_ticket=_percentile(tickets, 0.75),
        median_area=_median(areas),
        per_month=(len(current) / months) if months > 0 else None,
        by_construction_type=_by_construction_type(current),
        top_streets=_top_streets(current, top_streets, min_street_transactions),
    )


def _by_construction_type(sales: Sequence[Sale]) -> list[TypeStat]:
    groups: dict[str | None, list[Sale]] = defaultdict(list)
    for sale in sales:
        groups[sale.construction_type].append(sale)

    stats = [
            TypeStat(
                construction_type=code,
                label=CONSTRUCTION_TYPE_LABELS.get(code or "", code or "Não informado"),
                description=CONSTRUCTION_TYPE_DESCRIPTIONS.get(code or ""),
                transaction_count=len(group),
            median_price_per_m2=_median_m2(group),
        )
        for code, group in groups.items()
    ]
    stats.sort(key=lambda s: (s.median_price_per_m2 or 0), reverse=True)
    return stats


def _top_streets(
    sales: Sequence[Sale], limit: int, min_transactions: int
) -> list[StreetStat]:
    groups: dict[str, list[Sale]] = defaultdict(list)
    for sale in sales:
        groups[sale.street].append(sale)

    stats = [
        StreetStat(
            street=name,
            transaction_count=len(group),
            median_price_per_m2=_median_m2(group),
        )
        for name, group in groups.items()
        if len(group) >= min_transactions and _median_m2(group) is not None
    ]
    stats.sort(key=lambda s: (s.median_price_per_m2 or 0), reverse=True)
    return stats[:limit]


def occupation_mix(sales: Sequence[Sale]) -> list[tuple[str, int]]:
    """Most common occupation types, most frequent first."""
    counter = Counter((s.occupation_type or "Não informado") for s in sales)
    return counter.most_common()
