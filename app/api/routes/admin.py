"""Private operations API for ITBI/QuintoAndar condominium matching.

Production Basic Auth is applied by the reverse proxy, as for the ITBI upload.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.slugs import slugify
from app.models.portal_building import PortalBuilding
from app.models.transaction import Transaction
from app.services.condo_sync import sync_condos
from app.services.itbi_condominium_match import match_itbi_condominiums

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/api", tags=["admin"])
_CONDO_SYNC_LOCK = Lock()


class CondoSyncIn(BaseModel):
    city: str = "belo_horizonte"
    city_slug: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class MatchChoiceIn(BaseModel):
    building_id: int | None


def _area(value) -> float | None:
    return float(value) if value is not None else None


def _building_out(building: PortalBuilding) -> dict:
    return {
        "id": building.id,
        "external_id": building.external_id,
        "slug": building.slug,
        "url": building.url,
        "street": building.street,
        "street_number": building.street_number,
        "postal_code": building.postal_code,
        "neighborhood": building.neighborhood,
        "min_area_m2": _area(building.min_area),
        "max_area_m2": _area(building.max_area),
    }


@router.get("/cities")
def admin_cities(db: Session = Depends(get_db)) -> list[str]:
    transaction_cities = select(Transaction.city).distinct()
    building_cities = select(PortalBuilding.city).where(PortalBuilding.source == "quintoandar").distinct()
    return sorted(set(db.scalars(transaction_cities)).union(db.scalars(building_cities)))


@router.get("/overview")
def overview(city: str = "belo_horizonte", db: Session = Depends(get_db)) -> dict:
    counts = dict(
        db.execute(
            select(Transaction.condo_match_status, func.count())
            .where(Transaction.city == city)
            .group_by(Transaction.condo_match_status)
        ).all()
    )
    return {
        "city": city,
        "condominiums": db.scalar(
            select(func.count()).select_from(PortalBuilding).where(
                PortalBuilding.city == city,
                PortalBuilding.source == "quintoandar",
            )
        ) or 0,
        "transactions": db.scalar(
            select(func.count()).select_from(Transaction).where(Transaction.city == city)
        ) or 0,
        "matches": counts,
        "last_match_at": db.scalar(
            select(func.max(Transaction.condo_match_updated_at)).where(
                Transaction.city == city
            )
        ),
    }


@router.post("/condominiums/sync")
def sync_condominiums(payload: CondoSyncIn, db: Session = Depends(get_db)) -> dict:
    if not _CONDO_SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="coleta de condomínios já está em andamento")
    try:
        city_slug = payload.city_slug or slugify(payload.city.replace("_", " "))
        result = sync_condos(
            db,
            city=payload.city,
            city_slug=city_slug,
            limit=payload.limit,
            progress=lambda message: logger.info(message),
        )
        result["itbi_association"] = match_itbi_condominiums(db, city=payload.city)
        return result
    finally:
        _CONDO_SYNC_LOCK.release()


@router.post("/itbi/match")
def match_itbi(city: str = "belo_horizonte", db: Session = Depends(get_db)) -> dict:
    return match_itbi_condominiums(db, city=city)


@router.get("/itbi/matches")
def list_matches(
    city: str = "belo_horizonte",
    status: str = "ambiguous",
    q: str = "",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Transaction).where(Transaction.city == city)
    if status != "all":
        stmt = stmt.where(Transaction.condo_match_status == status)
    if q.strip():
        stmt = stmt.where(Transaction.raw_address.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Transaction.id.desc()).limit(limit).offset(offset)
    ).all()
    building_ids = {
        candidate_id
        for row in rows
        for candidate_id in (row.condo_match_candidates or [])
        if isinstance(candidate_id, int)
    }
    building_ids.update(row.portal_building_id for row in rows if row.portal_building_id)
    buildings = {
        item.id: item
        for item in db.scalars(
            select(PortalBuilding).where(
                PortalBuilding.id.in_(building_ids or {-1}),
                PortalBuilding.city == city,
                PortalBuilding.source == "quintoandar",
            )
        )
    }

    items = []
    for row in rows:
        ids = row.condo_match_candidates or []
        if row.portal_building_id and row.portal_building_id not in ids:
            ids = [*ids, row.portal_building_id]
        items.append(
            {
                "id": row.id,
                "raw_address": row.raw_address,
                "street": row.street,
                "street_number": row.street_number,
                "complement": row.complement,
                "postal_code": row.postal_code,
                "neighborhood": row.neighborhood,
                "settlement_date": row.settlement_date.isoformat(),
                "declared_value": float(row.declared_value),
                "built_area_acquired_m2": _area(row.built_area_acquired),
                "acquired_area_total_m2": _area(row.acquired_area_total),
                "status": row.condo_match_status,
                "score": row.condo_match_score,
                "evidence": row.condo_match_evidence or [],
                "selected_building_id": row.portal_building_id,
                "candidates": [
                    _building_out(buildings[candidate_id])
                    for candidate_id in ids
                    if candidate_id in buildings
                ],
            }
        )
    return {"total": total, "items": items, "limit": limit, "offset": offset}


@router.post("/itbi/transactions/{transaction_id}/match")
def choose_match(
    transaction_id: int,
    payload: MatchChoiceIn,
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(Transaction, transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="transação ITBI não encontrada")
    candidate_ids = set(row.condo_match_candidates or [])
    if row.portal_building_id:
        candidate_ids.add(row.portal_building_id)

    if payload.building_id is None:
        row.portal_building_id = None
        row.condo_match_status = "rejected"
        row.condo_match_score = None
        row.condo_match_evidence = ["manual_rejection"]
    else:
        if payload.building_id not in candidate_ids:
            raise HTTPException(status_code=400, detail="prédio não está entre os candidatos deste ITBI")
        building = db.get(PortalBuilding, payload.building_id)
        if building is None or building.city != row.city or building.source != "quintoandar":
            raise HTTPException(status_code=400, detail="prédio incompatível com a cidade desta transação")
        row.portal_building_id = building.id
        row.condo_match_status = "matched_manual"
        row.condo_match_score = 100
        row.condo_match_evidence = ["manual_selection"]

    row.condo_match_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"id": row.id, "status": row.condo_match_status, "building_id": row.portal_building_id}
