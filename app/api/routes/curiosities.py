"""City-wide trivia over the whole settled history.

Unlike the market views, these rankings cannot be windowed: "the unit that
changed hands the most times" only means something across every year on record.
That makes the endpoint a full scan, so the assembled board is memoized per
city and window, and invalidated by the data itself — a new ingestion moves
either the last settlement date or the row count, and the cached entry stops
matching.
"""

import threading
from collections import OrderedDict
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.curiosities import (
    Settlement,
    fastest_flips,
    neighborhood_spread,
    priciest_per_m2,
    priciest_sales,
    settlements_by_month,
    top_appreciation,
    top_buildings,
    top_units,
)
from app.domain.insights import InsightMetrics, available_insights
from app.domain.market_stats import Sale, neighborhood_ranking, shift_months
from app.domain.slugs import slugify
from app.models.transaction import Transaction
from app.schemas.curiosities import (
    AppreciationStatOut,
    BuildingStatOut,
    CuriositiesOut,
    CuriosityInsightsOut,
    FlipStatOut,
    MonthCountOut,
    MoverOut,
    NeighborhoodSpreadOut,
    RecordSaleOut,
    UnitRefOut,
    UnitStatOut,
)

router = APIRouter(prefix="/stats")

SETTLEMENT_COLUMNS = (
    Transaction.street,
    Transaction.street_number,
    Transaction.complement,
    Transaction.neighborhood,
    Transaction.settlement_date,
    Transaction.declared_value,
    Transaction.built_area_acquired,
    Transaction.acquired_fraction,
    Transaction.construction_type,
)

# yield_per keeps the DB cursor small; the board still materializes one
# Settlement per row (~524MB for 507k BH quitações). Production gives the
# web container 1GB and warms this cache on boot so the first visitor does
# not OOM the 512MB cgroup or freeze the only worker for the ~36s the scan
# takes there.
SCAN_CHUNK = 10_000

# The window is part of the key, not just the fingerprint: keying only by city
# meant a single `?months=36` visitor evicted the board warmed on boot, and the
# next visitor to the plain page paid the full scan again (~36s in production).
# The assembled boards are small (tens of KB), so keeping one per window costs
# far less than rebuilding one. LRU-bounded so an arbitrary `months` cannot grow
# the map without limit.
MAX_CACHED_BOARDS = 64

# (city, construction type, window) -> ((last settlement, row count), board)
_CACHE: OrderedDict[
    tuple[str | None, str | None, int], tuple[tuple[date | None, int], CuriositiesOut]
] = OrderedDict()
_BUILD_LOCK = threading.Lock()


def _scoped(stmt: Select, city: str | None, construction_type: str | None = None) -> Select:
    if city:
        stmt = stmt.where(Transaction.city == city)
    if construction_type:
        stmt = stmt.where(Transaction.construction_type == construction_type)
    return stmt


def _fingerprint(
    db: Session, city: str | None, construction_type: str | None = None
) -> tuple[date | None, int]:
    last = db.scalar(_scoped(select(func.max(Transaction.settlement_date)), city, construction_type))
    total = db.scalar(_scoped(select(func.count(Transaction.id)), city, construction_type)) or 0
    return last, total


def _fetch_settlements(
    db: Session, city: str | None, construction_type: str | None = None
) -> list[Settlement]:
    stmt = _scoped(select(*SETTLEMENT_COLUMNS), city, construction_type)
    return [
        Settlement(
            street=row.street,
            street_number=row.street_number,
            complement=row.complement,
            neighborhood=row.neighborhood,
            settlement_date=row.settlement_date,
            declared_value=float(row.declared_value),
            built_area_acquired=(
                float(row.built_area_acquired)
                if row.built_area_acquired is not None
                else None
            ),
            acquired_fraction=(
                float(row.acquired_fraction)
                if row.acquired_fraction is not None
                else None
            ),
            construction_type=row.construction_type,
        )
        for row in db.execute(stmt).yield_per(SCAN_CHUNK)
    ]


def _unit_out(unit) -> UnitRefOut:
    return UnitRefOut(
        street=unit.street,
        street_number=unit.street_number,
        complement=unit.complement,
        neighborhood=unit.neighborhood,
    )


def _building_out(stat) -> BuildingStatOut:
    return BuildingStatOut(
        street=stat.street,
        street_number=stat.street_number,
        neighborhood=stat.neighborhood,
        transaction_count=stat.transaction_count,
        unit_count=stat.unit_count,
        median_price_per_m2=stat.median_price_per_m2,
        last_settlement_date=stat.last_settlement_date,
    )


def _record_out(stat) -> RecordSaleOut:
    return RecordSaleOut(
        unit=_unit_out(stat.unit),
        settlement_date=stat.settlement_date,
        declared_value=stat.declared_value,
        built_area_acquired=stat.built_area_acquired,
        price_per_m2=stat.price_per_m2,
        construction_type=stat.construction_type,
    )


def _movers(
    settlements: list[Settlement], reference: date, months: int, min_transactions: int
) -> tuple[list[MoverOut], list[MoverOut]]:
    """Neighborhoods that moved the most in the window, both directions."""
    window_start = shift_months(reference, months * 2)
    sales = [
        Sale(
            neighborhood=s.neighborhood,
            street=s.street,
            settlement_date=s.settlement_date,
            declared_value=s.declared_value,
            built_area_acquired=s.built_area_acquired,
            construction_type=s.construction_type,
            occupation_type=None,
        )
        for s in settlements
        if window_start < s.settlement_date <= reference
    ]
    ranked = [
        stat
        for stat in neighborhood_ranking(
            sales,
            reference=reference,
            months=months,
            min_transactions=min_transactions,
        )
        if stat.delta_pct is not None
    ]
    ranked.sort(key=lambda s: s.delta_pct, reverse=True)

    def out(stats) -> list[MoverOut]:
        return [
            MoverOut(
                neighborhood=s.neighborhood,
                transaction_count=s.transaction_count,
                median_price_per_m2=s.median_price_per_m2,
                delta_pct=s.delta_pct,
            )
            for s in stats
        ]

    risers, fallers = _split_movers(ranked)
    return out(risers), out(fallers)


def _split_movers(ranked: list) -> tuple[list, list]:
    """Keep rising and falling neighborhoods in their own rankings."""
    risers = [item for item in ranked if item.delta_pct > 0][:10]
    fallers = sorted(
        (item for item in ranked if item.delta_pct < 0),
        key=lambda item: item.delta_pct,
    )[:10]
    return risers, fallers


def _build(
    db: Session, city: str | None, months: int, construction_type: str | None = None
) -> CuriositiesOut:
    settlements = _fetch_settlements(db, city, construction_type)
    if not settlements:
        return CuriositiesOut(
            city=city,
            reference_date=None,
            months=months,
            transaction_count=0,
            top_buildings=[],
            top_buildings_recent=[],
            top_units=[],
            top_appreciation=[],
            fastest_flips=[],
            priciest_sales=[],
            priciest_per_m2=[],
            by_month=[],
            risers=[],
            fallers=[],
            widest_spread=[],
        )

    reference = max(s.settlement_date for s in settlements)
    window_start = shift_months(reference, months)
    recent = [s for s in settlements if window_start < s.settlement_date <= reference]
    risers, fallers = _movers(settlements, reference, months, min_transactions=20)

    return CuriositiesOut(
        city=city,
        reference_date=reference,
        months=months,
        transaction_count=len(settlements),
        top_buildings=[_building_out(s) for s in top_buildings(settlements)],
        top_buildings_recent=[_building_out(s) for s in top_buildings(recent)],
        top_units=[
            UnitStatOut(
                unit=_unit_out(s.unit),
                transaction_count=s.transaction_count,
                first_settlement_date=s.first_settlement_date,
                last_settlement_date=s.last_settlement_date,
                last_value=s.last_value,
            )
            for s in top_units(settlements)
        ],
        top_appreciation=[
            AppreciationStatOut(
                unit=_unit_out(s.unit),
                from_date=s.from_date,
                from_value=s.from_value,
                to_date=s.to_date,
                to_value=s.to_value,
                total_pct=s.total_pct,
                years=s.years,
                annualized_pct=s.annualized_pct,
            )
            for s in top_appreciation(settlements)
        ],
        fastest_flips=[
            FlipStatOut(
                unit=_unit_out(s.unit),
                from_date=s.from_date,
                from_value=s.from_value,
                to_date=s.to_date,
                to_value=s.to_value,
                days=s.days,
                delta_pct=s.delta_pct,
            )
            for s in fastest_flips(settlements)
        ],
        priciest_sales=[_record_out(s) for s in priciest_sales(settlements)],
        priciest_per_m2=[_record_out(s) for s in priciest_per_m2(settlements)],
        by_month=[
            MonthCountOut(
                year=m.year, month=m.month, transaction_count=m.transaction_count
            )
            for m in settlements_by_month(settlements)
        ],
        risers=risers,
        fallers=fallers,
        widest_spread=[
            NeighborhoodSpreadOut(
                neighborhood=s.neighborhood,
                transaction_count=s.transaction_count,
                p25_ticket=s.p25_ticket,
                median_ticket=s.median_ticket,
                p75_ticket=s.p75_ticket,
                spread_ratio=s.spread_ratio,
            )
            for s in neighborhood_spread(settlements, reference=reference, months=months)
        ],
    )


def _cached_board(
    db: Session, city: str | None, months: int, construction_type: str | None
) -> CuriositiesOut:
    """Return the memoized board, building it at most once per cache key."""
    cache_key = (city, construction_type, months)
    fingerprint = _fingerprint(db, city, construction_type)
    cached = _CACHE.get(cache_key)
    if cached and cached[0] == fingerprint:
        _CACHE.move_to_end(cache_key)
        return cached[1]

    with _BUILD_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] == fingerprint:
            _CACHE.move_to_end(cache_key)
            return cached[1]
        board = _build(db, city, months, construction_type)
        _CACHE[cache_key] = (fingerprint, board)
        _CACHE.move_to_end(cache_key)
        while len(_CACHE) > MAX_CACHED_BOARDS:
            _CACHE.popitem(last=False)
        return board


def warm_default_curiosities(db: Session) -> None:
    """Pre-build the default (no type filter, 12-month) board for every city."""
    cities = list(db.scalars(select(Transaction.city).distinct()))
    for city in cities:
        _cached_board(db, city, months=12, construction_type=None)


@router.get("/curiosities", response_model=CuriositiesOut)
def get_curiosities(
    city: str | None = None,
    months: int = Query(12, ge=1, le=120),
    construction_type: str | None = Query(None, min_length=2, max_length=2),
    db: Session = Depends(get_db),
) -> CuriositiesOut:
    """Every trivia list for one city, computed once per ingestion."""
    return _cached_board(db, city, months, construction_type)


@router.get("/curiosities/insights", response_model=CuriosityInsightsOut)
def get_curiosity_insights(
    city: str = Query(...),
    db: Session = Depends(get_db),
) -> CuriosityInsightsOut:
    """Return the eligible, linkable curiosity pages for one city."""
    board = _cached_board(db, city, months=12, construction_type=None)
    metrics = InsightMetrics(
        transaction_count=board.transaction_count,
        appreciation_count=len(board.top_appreciation),
        flip_count=len(board.fastest_flips),
        priciest_sale_count=len(board.priciest_sales),
        riser_count=len(board.risers),
        building_count=len(board.top_buildings),
    )
    return CuriosityInsightsOut(
        city=city,
        transaction_count=board.transaction_count,
        items=[
            {
                "slug": item.slug,
                "title": item.title,
                "description": item.description,
                "count": item.count,
                "url": item.url,
            }
            for item in available_insights(slugify(city), metrics)
        ],
    )
