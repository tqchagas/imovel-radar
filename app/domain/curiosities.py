"""City-wide oddities built from settled ITBI rows.

Everything here is pure: routes fetch the rows, these functions summarize them.
The lists are meant to be read as trivia, so they are filtered harder than the
market views — a symbolic R$ 1,00 transfer or a 2 m² storage box would top most
rankings and say nothing true about the city.

Unit identity follows `property_history`: the same normalized complement at the
same street and number. "Full sale" also follows it — BH stores the condo ideal
fraction, so a sale is treated as partial when its fraction falls well below the
largest one that unit ever recorded.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

from app.domain.complement import normalize_complement, normalize_street_key
from app.domain.market_stats import shift_months

# Symbolic transfers (inheritance, donations, corrections) sit far below any
# real price and would otherwise win every "biggest appreciation" ranking.
MIN_REAL_VALUE = 50_000.0
# Parking spots and storage boxes are real sales, but their R$/m² is not
# comparable to a home's — they distort the price records.
MIN_RECORD_AREA = 40.0
# A row whose R$/m² is an order of magnitude above the city is not the priciest
# home in town, it is a value that covers more than the area it declares.
RECORD_M2_CEILING_RATIO = 10.0
# Two sales of the same unit whose areas disagree this much are not the same
# asset: usually a lot bought before the building went up.
AREA_DIVERGENCE_RATIO = 0.20
FULL_FRACTION_RATIO = 0.90
# A first sale this far under what its neighborhood charged that year is an
# off-plan purchase or a swap with the developer, not a market price. Ranking
# from it turns "the developer sold cheap" into "this unit appreciated 1.400%".
MIN_BASELINE_RATIO = 0.40
# Below this many rows a neighborhood-year median is noise; fall back to the city.
MIN_BASELINE_SAMPLE = 5


@dataclass(frozen=True, slots=True)
class Settlement:
    """The slice of a transaction the curiosity views need."""

    street: str
    street_number: str | None
    complement: str | None
    neighborhood: str
    settlement_date: date
    declared_value: float
    built_area_acquired: float | None
    acquired_fraction: float | None
    construction_type: str | None


@dataclass(frozen=True, slots=True)
class UnitRef:
    """Everything the front end needs to link back to `/imovel`."""

    street: str
    street_number: str | None
    complement: str | None
    neighborhood: str


@dataclass
class BuildingStat:
    street: str
    street_number: str | None
    neighborhood: str
    transaction_count: int
    unit_count: int
    median_price_per_m2: float | None
    last_settlement_date: date


@dataclass
class UnitStat:
    unit: UnitRef
    transaction_count: int
    first_settlement_date: date
    last_settlement_date: date
    last_value: float


@dataclass
class AppreciationStat:
    unit: UnitRef
    from_date: date
    from_value: float
    to_date: date
    to_value: float
    total_pct: float
    years: float
    annualized_pct: float


@dataclass
class FlipStat:
    unit: UnitRef
    from_date: date
    from_value: float
    to_date: date
    to_value: float
    days: int
    delta_pct: float


@dataclass
class RecordSale:
    unit: UnitRef
    settlement_date: date
    declared_value: float
    built_area_acquired: float | None
    price_per_m2: float | None
    construction_type: str | None


@dataclass
class MonthCount:
    year: int
    month: int
    transaction_count: int


@dataclass
class NeighborhoodSpread:
    neighborhood: str
    transaction_count: int
    p25_ticket: float
    median_ticket: float
    p75_ticket: float
    spread_ratio: float


def _price_per_m2(value: float, area: float | None) -> float | None:
    if area is None or area <= 0:
        return None
    return value / area


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


def unit_key(sale: Settlement) -> tuple[str, str, str | None]:
    return (
        normalize_street_key(sale.street),
        normalize_street_key(sale.street_number),
        normalize_complement(sale.complement),
    )


def building_key(sale: Settlement) -> tuple[str, str]:
    return normalize_street_key(sale.street), normalize_street_key(sale.street_number)


def _unit_ref(sale: Settlement) -> UnitRef:
    return UnitRef(
        street=sale.street,
        street_number=sale.street_number,
        complement=sale.complement,
        neighborhood=sale.neighborhood,
    )


def group_units(
    sales: Iterable[Settlement],
) -> dict[tuple[str, str, str | None], list[Settlement]]:
    """Settlements grouped by unit identity, each group in chronological order."""
    groups: dict[tuple[str, str, str | None], list[Settlement]] = defaultdict(list)
    for sale in sales:
        groups[unit_key(sale)].append(sale)
    for group in groups.values():
        group.sort(key=lambda s: s.settlement_date)
    return groups


def identified_units(
    sales: Iterable[Settlement],
) -> list[list[Settlement]]:
    """Unit groups that name an actual unit.

    Rows with no usable complement all fall into the lot-level bucket of their
    address — at a 700-unit tower that bucket holds hundreds of unrelated
    apartments. Counting it as "one unit sold 322 times" would be false, so the
    unit-level rankings only look at addressable units.
    """
    return [
        group
        for key, group in group_units(sales).items()
        if key[2] is not None
    ]


class PriceBaseline:
    """Median R$/m² per neighborhood and year, with the city as fallback.

    Used to tell a market price from a developer's price: both are real
    settlements, only one says something about what the unit was worth.
    """

    def __init__(self, sales: Iterable[Settlement]) -> None:
        by_area: dict[tuple[str, int], list[float]] = defaultdict(list)
        by_year: dict[int, list[float]] = defaultdict(list)
        for sale in sales:
            m2 = _price_per_m2(sale.declared_value, sale.built_area_acquired)
            if m2 is None:
                continue
            by_area[(sale.neighborhood, sale.settlement_date.year)].append(m2)
            by_year[sale.settlement_date.year].append(m2)

        self._local = {
            key: _median(values)
            for key, values in by_area.items()
            if len(values) >= MIN_BASELINE_SAMPLE
        }
        self._city = {year: _median(values) for year, values in by_year.items()}

    def for_sale(self, sale: Settlement) -> float | None:
        local = self._local.get((sale.neighborhood, sale.settlement_date.year))
        return local if local is not None else self._city.get(sale.settlement_date.year)

    def is_market_price(self, sale: Settlement) -> bool:
        """False when the row is far below what its neighborhood charged then."""
        m2 = _price_per_m2(sale.declared_value, sale.built_area_acquired)
        baseline = self.for_sale(sale)
        if m2 is None or baseline is None or baseline <= 0:
            return False
        return m2 >= baseline * MIN_BASELINE_RATIO


def _areas_comparable(a: Settlement, b: Settlement) -> bool:
    """Whether two settlements plausibly describe the same physical asset."""
    if a.built_area_acquired is None or b.built_area_acquired is None:
        return True
    if a.built_area_acquired <= 0 or b.built_area_acquired <= 0:
        return True
    smaller = min(a.built_area_acquired, b.built_area_acquired)
    gap = abs(a.built_area_acquired - b.built_area_acquired) / smaller
    return gap <= AREA_DIVERGENCE_RATIO


def full_sales(group: Sequence[Settlement]) -> list[Settlement]:
    """Drop the partial-share rows, so a 5% cota is not read as a price drop."""
    fractions = [s.acquired_fraction for s in group if s.acquired_fraction is not None]
    if not fractions:
        return list(group)
    threshold = max(fractions) * FULL_FRACTION_RATIO
    return [
        s
        for s in group
        if s.acquired_fraction is None or s.acquired_fraction >= threshold
    ]


def top_buildings(
    sales: Sequence[Settlement], limit: int = 20, min_transactions: int = 2
) -> list[BuildingStat]:
    """Addresses with the most settlements — the city's busiest doors."""
    groups: dict[tuple[str, str], list[Settlement]] = defaultdict(list)
    for sale in sales:
        groups[building_key(sale)].append(sale)

    stats = []
    for group in groups.values():
        if len(group) < min_transactions:
            continue
        newest = max(group, key=lambda s: s.settlement_date)
        m2 = [
            value
            for value in (
                _price_per_m2(s.declared_value, s.built_area_acquired) for s in group
            )
            if value is not None
        ]
        stats.append(
            BuildingStat(
                street=newest.street,
                street_number=newest.street_number,
                neighborhood=newest.neighborhood,
                transaction_count=len(group),
                unit_count=len({unit_key(s) for s in group}),
                median_price_per_m2=_median(m2),
                last_settlement_date=newest.settlement_date,
            )
        )

    stats.sort(key=lambda s: (s.transaction_count, s.last_settlement_date), reverse=True)
    return stats[:limit]


def top_units(
    sales: Sequence[Settlement],
    limit: int = 30,
    min_transactions: int = 2,
    max_per_building: int = 3,
) -> list[UnitStat]:
    """Units that changed hands the most times.

    Capped per address: one share-owned tower can hold a hundred units with
    near-identical counts, and thirty rows of the same building is a worse list
    than thirty buildings.
    """
    ranked: list[tuple[tuple[str, str], UnitStat]] = []
    for group in identified_units(sales):
        if len(group) < min_transactions:
            continue
        ranked.append(
            (
                building_key(group[-1]),
                UnitStat(
                    unit=_unit_ref(group[-1]),
                    transaction_count=len(group),
                    first_settlement_date=group[0].settlement_date,
                    last_settlement_date=group[-1].settlement_date,
                    last_value=group[-1].declared_value,
                ),
            )
        )

    ranked.sort(
        key=lambda pair: (pair[1].transaction_count, pair[1].last_settlement_date),
        reverse=True,
    )

    seen: dict[tuple[str, str], int] = defaultdict(int)
    stats = []
    for key, stat in ranked:
        if seen[key] >= max_per_building:
            continue
        seen[key] += 1
        stats.append(stat)
        if len(stats) == limit:
            break
    return stats


def top_appreciation(
    sales: Sequence[Settlement],
    limit: int = 20,
    min_years: float = 3.0,
) -> list[AppreciationStat]:
    """Biggest gain between the first and last full sale of the same unit.

    Annualized alongside the total: eighteen years of inflation dressed up as
    "+900%" is a worse story than what the unit actually did per year. Pairs
    whose areas disagree are dropped — a lot bought before the tower went up is
    not a unit that appreciated — and so are pairs whose first sale sits far
    under its neighborhood's price that year.
    """
    baseline = PriceBaseline(sales)
    stats = []
    for group in identified_units(sales):
        full = full_sales(group)
        if len(full) < 2:
            continue
        first, last = full[0], full[-1]
        if first.declared_value < MIN_REAL_VALUE or last.declared_value < MIN_REAL_VALUE:
            continue
        if not _areas_comparable(first, last):
            continue
        if not baseline.is_market_price(first):
            continue

        years = (last.settlement_date - first.settlement_date).days / 365.25
        if years < min_years:
            continue

        total_pct = (last.declared_value / first.declared_value - 1) * 100
        stats.append(
            AppreciationStat(
                unit=_unit_ref(last),
                from_date=first.settlement_date,
                from_value=first.declared_value,
                to_date=last.settlement_date,
                to_value=last.declared_value,
                total_pct=total_pct,
                years=years,
                annualized_pct=((last.declared_value / first.declared_value) ** (1 / years) - 1)
                * 100,
            )
        )

    stats.sort(key=lambda s: s.annualized_pct, reverse=True)
    return stats[:limit]


def fastest_flips(
    sales: Sequence[Settlement], limit: int = 20, min_days: int = 7
) -> list[FlipStat]:
    """Shortest gap between two full sales of the same unit.

    `min_days` drops anything inside a week: two rows that close days apart are
    registry mechanics — one deal split across spouses, shares or a correction —
    not somebody buying and reselling.
    """
    stats = []
    for group in identified_units(sales):
        full = full_sales(group)
        if len(full) < 2:
            continue

        for previous, current in zip(full, full[1:]):
            days = (current.settlement_date - previous.settlement_date).days
            if days < min_days:
                continue
            if (
                previous.declared_value < MIN_REAL_VALUE
                or current.declared_value < MIN_REAL_VALUE
            ):
                continue
            if not _areas_comparable(previous, current):
                continue
            stats.append(
                FlipStat(
                    unit=_unit_ref(current),
                    from_date=previous.settlement_date,
                    from_value=previous.declared_value,
                    to_date=current.settlement_date,
                    to_value=current.declared_value,
                    days=days,
                    delta_pct=(current.declared_value / previous.declared_value - 1) * 100,
                )
            )

    stats.sort(key=lambda s: (s.days, -s.to_value))
    return stats[:limit]


def priciest_sales(sales: Sequence[Settlement], limit: int = 10) -> list[RecordSale]:
    """Highest declared values on record."""
    ordered = sorted(sales, key=lambda s: s.declared_value, reverse=True)
    return [_record(s) for s in ordered[:limit]]


def priciest_per_m2(sales: Sequence[Settlement], limit: int = 10) -> list[RecordSale]:
    """Highest R$/m² among rows big enough — and sane enough — to compare.

    Beyond the area floor there is a ceiling relative to the city's own median:
    a row ten times above it is a declared value that covers more than the area
    it reports, not the priciest square metre in town.
    """
    eligible = [
        (m2, sale)
        for sale in sales
        if sale.built_area_acquired is not None
        and sale.built_area_acquired >= MIN_RECORD_AREA
        and sale.declared_value >= MIN_REAL_VALUE
        and (m2 := _price_per_m2(sale.declared_value, sale.built_area_acquired))
        is not None
    ]
    if not eligible:
        return []

    ceiling = (_median([m2 for m2, _ in eligible]) or 0) * RECORD_M2_CEILING_RATIO
    plausible = [pair for pair in eligible if pair[0] <= ceiling]
    plausible.sort(key=lambda pair: pair[0], reverse=True)
    return [_record(sale) for _, sale in plausible[:limit]]


def _record(sale: Settlement) -> RecordSale:
    return RecordSale(
        unit=_unit_ref(sale),
        settlement_date=sale.settlement_date,
        declared_value=sale.declared_value,
        built_area_acquired=sale.built_area_acquired,
        price_per_m2=_price_per_m2(sale.declared_value, sale.built_area_acquired),
        construction_type=sale.construction_type,
    )


def settlements_by_month(sales: Sequence[Settlement]) -> list[MonthCount]:
    """Monthly settlement counts, oldest first — the city's transaction rhythm."""
    counts: dict[tuple[int, int], int] = defaultdict(int)
    for sale in sales:
        counts[(sale.settlement_date.year, sale.settlement_date.month)] += 1
    return [
        MonthCount(year=year, month=month, transaction_count=count)
        for (year, month), count in sorted(counts.items())
    ]


def neighborhood_spread(
    sales: Sequence[Settlement],
    reference: date,
    months: int = 12,
    limit: int = 10,
    min_transactions: int = 20,
) -> list[NeighborhoodSpread]:
    """Neighborhoods where the cheapest and priciest deals are furthest apart.

    A high ratio means the name of the neighborhood tells you very little about
    what you will pay there.
    """
    start = shift_months(reference, months)
    tickets: dict[str, list[float]] = defaultdict(list)
    for sale in sales:
        # Symbolic transfers sit in the bottom quartile and would turn every
        # neighborhood that saw one into the most unequal in town.
        if (
            start < sale.settlement_date <= reference
            and sale.declared_value >= MIN_REAL_VALUE
        ):
            tickets[sale.neighborhood].append(sale.declared_value)

    stats = []
    for name, values in tickets.items():
        if len(values) < min_transactions:
            continue
        p25 = _percentile(values, 0.25)
        p75 = _percentile(values, 0.75)
        median = _median(values)
        if not p25 or not p75 or median is None:
            continue
        stats.append(
            NeighborhoodSpread(
                neighborhood=name,
                transaction_count=len(values),
                p25_ticket=p25,
                median_ticket=median,
                p75_ticket=p75,
                spread_ratio=p75 / p25,
            )
        )

    stats.sort(key=lambda s: s.spread_ratio, reverse=True)
    return stats[:limit]
