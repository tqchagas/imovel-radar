"""Listing opportunities: active listings priced below their ITBI reference."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.opportunities import CONFIDENCE_ORDER
from app.domain.slugs import address_key
from app.models.market_comparable import MarketComparable
from app.schemas.opportunities import (
    OpportunityListOut,
    OpportunityOut,
    OpportunitySummaryOut,
)

router = APIRouter()

SORTS = {
    "desconto_desc": MarketComparable.desconto_pct.desc(),
    "desconto_asc": MarketComparable.desconto_pct.asc(),
    "preco_asc": MarketComparable.preco_total.asc(),
    "preco_desc": MarketComparable.preco_total.desc(),
    "recente_desc": MarketComparable.first_seen_at.desc(),
}


def _as_float(value) -> float | None:
    return float(value) if value is not None else None


def _calculated() -> Select:
    return select(MarketComparable).where(
        MarketComparable.ativo.is_(True),
        MarketComparable.preco_estimado.is_not(None),
        MarketComparable.desconto_pct.is_not(None),
        MarketComparable.confianca.is_not(None),
    )


def _filtered(
    city: str | None,
    neighborhood: str | None,
    source: str | None,
    tipo_imovel: str | None,
    confianca: str | None,
    min_confianca: str | None,
    min_desconto_pct: float | None,
    max_preco: float | None,
) -> Select:
    stmt = _calculated()
    if city:
        stmt = stmt.where(MarketComparable.cidade_normalizada == address_key(city))
    if neighborhood:
        stmt = stmt.where(MarketComparable.bairro_normalizado == address_key(neighborhood))
    if source:
        stmt = stmt.where(MarketComparable.source == source)
    if tipo_imovel:
        stmt = stmt.where(MarketComparable.tipo_imovel == tipo_imovel.upper())
    if confianca:
        stmt = stmt.where(MarketComparable.confianca == confianca)
    if min_confianca:
        allowed = [
            level
            for level, rank in CONFIDENCE_ORDER.items()
            if rank >= CONFIDENCE_ORDER[min_confianca]
        ]
        stmt = stmt.where(MarketComparable.confianca.in_(allowed))
    if min_desconto_pct is not None:
        stmt = stmt.where(MarketComparable.desconto_pct >= min_desconto_pct)
    if max_preco is not None:
        stmt = stmt.where(MarketComparable.preco_total <= max_preco)
    return stmt


def _to_out(row: MarketComparable) -> OpportunityOut:
    return OpportunityOut(
        id=row.id,
        source=row.source,
        listing_id=row.listing_id,
        url=row.url,
        cidade=row.cidade,
        bairro=row.bairro,
        rua=row.rua,
        numero=row.numero,
        tipo_imovel=row.tipo_imovel,
        quartos=row.bedrooms,
        banheiros=row.bathrooms,
        vagas=row.parking_spaces,
        area_util_m2=_as_float(row.area_util_m2),
        preco_anunciado=_as_float(row.preco_total),
        preco_estimado=_as_float(row.preco_estimado),
        desconto_pct=_as_float(row.desconto_pct),
        desconto_reais=_as_float(row.desconto_reais),
        tipo_referencia=row.tipo_referencia,
        amostra_count=row.amostra_count,
        referencia_data_inicio=row.referencia_data_inicio,
        referencia_data_fim=row.referencia_data_fim,
        confianca=row.confianca,
        motivos=[line for line in (row.oportunidade_motivo or "").split("\n") if line],
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
    )


@router.get("/opportunities", response_model=OpportunityListOut)
def list_opportunities(
    city: str | None = None,
    neighborhood: str | None = None,
    source: str | None = None,
    tipo_imovel: str | None = None,
    confianca: str | None = None,
    min_confianca: str | None = None,
    min_desconto_pct: float | None = None,
    max_preco: float | None = None,
    sort: str = Query("desconto_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, gt=0, le=200),
    db: Session = Depends(get_db),
) -> OpportunityListOut:
    if sort not in SORTS:
        raise HTTPException(
            status_code=400, detail=f"Unknown sort '{sort}'. Available: {list(SORTS)}"
        )
    for level in (confianca, min_confianca):
        if level and level not in CONFIDENCE_ORDER:
            raise HTTPException(status_code=400, detail=f"Unknown confidence '{level}'")

    stmt = _filtered(
        city,
        neighborhood,
        source,
        tipo_imovel,
        confianca,
        min_confianca,
        min_desconto_pct,
        max_preco,
    )
    scoped = stmt.subquery()
    total = db.scalar(select(func.count()).select_from(scoped)) or 0
    summary = db.execute(
        select(
            func.max(scoped.c.desconto_pct),
            func.max(scoped.c.last_seen_at),
            func.max(scoped.c.referencia_data_fim),
        )
    ).one()
    items = db.scalars(
        # id breaks ties so paging stays stable across requests.
        stmt.order_by(SORTS[sort], MarketComparable.id.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return OpportunityListOut(
        city=address_key(city) if city else None,
        total=total,
        page=page,
        page_size=page_size,
        summary=OpportunitySummaryOut(
            total=total,
            max_desconto_pct=_as_float(summary[0]),
            last_collected_at=summary[1],
            reference_date=summary[2],
        ),
        items=[_to_out(row) for row in items],
    )


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(
    opportunity_id: int, db: Session = Depends(get_db)
) -> OpportunityOut:
    row = db.scalar(_calculated().where(MarketComparable.id == opportunity_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return _to_out(row)
