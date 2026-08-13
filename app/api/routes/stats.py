from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.market_stats import (
    Sale,
    neighborhood_detail,
    neighborhood_ranking,
    shift_months,
)
from app.domain.street_stats import street_detail
from app.models.transaction import Transaction
from app.schemas.stats import (
    NeighborhoodDetailOut,
    NeighborhoodRankingOut,
    NeighborhoodStatOut,
    OverviewOut,
    StreetAddressStatOut,
    StreetDetailOut,
    StreetStatOut,
    TypeStatOut,
)
from app.services.market_data import fetch_sales, reference_date, scoped

router = APIRouter(prefix="/stats")

_scoped = scoped
_reference_date = reference_date
_fetch_sales = fetch_sales


@router.get("/overview", response_model=OverviewOut)
def get_overview(
    city: str | None = None,
    db: Session = Depends(get_db),
) -> OverviewOut:
    """Headline counters for the landing page."""
    total = db.scalar(_scoped(select(func.count(Transaction.id)), city)) or 0
    neighborhoods = (
        db.scalar(
            _scoped(
                select(func.count(func.distinct(Transaction.neighborhood))),
                city,
            )
        )
        or 0
    )

    first = db.scalar(_scoped(select(func.min(Transaction.settlement_date)), city))
    last = db.scalar(_scoped(select(func.max(Transaction.settlement_date)), city))

    return OverviewOut(
        city=city,
        transaction_count=total,
        neighborhood_count=neighborhoods,
        year_from=first.year if first else None,
        year_to=last.year if last else None,
        last_settlement_date=last,
    )

@router.get("/streets/{street}", response_model=StreetDetailOut)
def get_street_detail(
    street: str,
    city: str = Query(...),
    months: int = Query(12, ge=1, le=120),
    db: Session = Depends(get_db),
) -> StreetDetailOut:
    reference = _reference_date(db, city)
    if reference is None:
        raise HTTPException(status_code=404, detail="City has no transactions")

    sales = _fetch_sales(db, city, shift_months(reference, months * 2), reference)
    detail = street_detail(sales, street=street, reference=reference, months=months)
    if not detail.transaction_count:
        raise HTTPException(status_code=404, detail="Street not found")

    return StreetDetailOut(
        city=city,
        street=detail.street,
        months=months,
        reference_date=reference,
        transaction_count=detail.transaction_count,
        property_count=detail.property_count,
        median_ticket=detail.median_ticket,
        p25_ticket=detail.p25_ticket,
        p75_ticket=detail.p75_ticket,
        median_area=detail.median_area,
        median_price_per_m2=detail.median_price_per_m2,
        top_addresses=[
            StreetAddressStatOut(
                street_number=address.street_number,
                transaction_count=address.transaction_count,
                median_price_per_m2=address.median_price_per_m2,
                last_settlement_date=address.last_settlement_date,
            )
            for address in detail.top_addresses
        ],
    )
@router.get("/neighborhoods", response_model=NeighborhoodRankingOut)
def get_neighborhood_ranking(
    city: str | None = None,
    months: int = Query(12, ge=1, le=120),
    limit: int = Query(20, ge=1, le=500),
    min_transactions: int = Query(5, ge=1),
    db: Session = Depends(get_db),
) -> NeighborhoodRankingOut:
    """Neighborhoods ranked by median R$/m², with the change vs. the prior window."""
    reference = _reference_date(db, city)
    if reference is None:
        return NeighborhoodRankingOut(
            city=city, months=months, reference_date=None, items=[]
        )

    sales = _fetch_sales(db, city, shift_months(reference, months * 2), reference)
    ranking = neighborhood_ranking(
        sales,
        reference=reference,
        months=months,
        limit=limit,
        min_transactions=min_transactions,
    )
    return NeighborhoodRankingOut(
        city=city,
        months=months,
        reference_date=reference,
        items=[
            NeighborhoodStatOut(
                neighborhood=s.neighborhood,
                transaction_count=s.transaction_count,
                median_price_per_m2=s.median_price_per_m2,
                delta_pct=s.delta_pct,
            )
            for s in ranking
        ],
    )


@router.get("/neighborhoods/{neighborhood}", response_model=NeighborhoodDetailOut)
def get_neighborhood_detail(
    neighborhood: str,
    city: str = Query(...),
    months: int = Query(12, ge=1, le=120),
    db: Session = Depends(get_db),
) -> NeighborhoodDetailOut:
    reference = _reference_date(db, city)
    if reference is None:
        raise HTTPException(status_code=404, detail="City has no transactions")

    sales = _fetch_sales(
        db,
        city,
        shift_months(reference, months * 2),
        reference,
        neighborhood=neighborhood,
    )
    if not sales:
        raise HTTPException(status_code=404, detail="Neighborhood not found")

    detail = neighborhood_detail(
        sales, neighborhood=neighborhood, reference=reference, months=months
    )
    return NeighborhoodDetailOut(
        city=city,
        neighborhood=detail.neighborhood,
        months=months,
        reference_date=reference,
        transaction_count=detail.transaction_count,
        residential_share_pct=detail.residential_share_pct,
        median_price_per_m2=detail.median_price_per_m2,
        delta_pct=detail.delta_pct,
        median_ticket=detail.median_ticket,
        p25_ticket=detail.p25_ticket,
        p75_ticket=detail.p75_ticket,
        median_area=detail.median_area,
        per_month=detail.per_month,
        by_construction_type=[
            TypeStatOut(
                construction_type=t.construction_type,
                label=t.label,
                description=t.description,
                transaction_count=t.transaction_count,
                median_price_per_m2=t.median_price_per_m2,
            )
            for t in detail.by_construction_type
        ],
        top_streets=[
            StreetStatOut(
                street=s.street,
                transaction_count=s.transaction_count,
                median_price_per_m2=s.median_price_per_m2,
            )
            for s in detail.top_streets
        ],
    )
