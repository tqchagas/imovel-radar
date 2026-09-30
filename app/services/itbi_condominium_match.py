"""Associate ITBI addresses with already collected QuintoAndar buildings."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.slugs import address_key, street_key
from app.models.portal_building import PortalBuilding
from app.models.transaction import Transaction

BATCH_SIZE = 1_000
REPROCESS_STATUSES = ("pending", "not_found", "ambiguous")


@dataclass(frozen=True)
class BuildingCandidate:
    id: int
    city: str
    street_key: str
    number_key: str
    postal_code: str | None


def _building_index(db: Session, city: str) -> dict[tuple[str, str, str], list[BuildingCandidate]]:
    groups: dict[tuple[str, str, str], list[BuildingCandidate]] = defaultdict(list)
    rows = db.execute(
        select(
            PortalBuilding.id,
            PortalBuilding.city,
            PortalBuilding.street_key,
            PortalBuilding.number_key,
            PortalBuilding.postal_code,
        ).where(
            PortalBuilding.city == city,
            PortalBuilding.source == "quintoandar",
            PortalBuilding.street_key.is_not(None),
            PortalBuilding.number_key.is_not(None),
        )
    )
    for row in rows:
        building = BuildingCandidate(
            id=row.id,
            city=row.city,
            street_key=row.street_key,
            number_key=row.number_key,
            postal_code=row.postal_code,
        )
        key = (building.city, building.street_key, building.number_key)
        groups[key].append(building)
    return groups


def _match_values(
    row: Any, buildings: list[BuildingCandidate] | None, *, matched_at: datetime
) -> dict[str, Any]:
    street = street_key(row.street)
    number = address_key(row.street_number)
    if not street or not number:
        return {
            "portal_building_id": None,
            "condo_match_status": "insufficient_address",
            "condo_match_score": None,
            "condo_match_evidence": ["street_or_number_missing"],
            "condo_match_candidates": [],
            "condo_match_updated_at": matched_at,
        }

    candidates = list(buildings or [])
    evidence = ["city", "normalized_street", "street_number"]
    if not candidates:
        return {
            "portal_building_id": None,
            "condo_match_status": "not_found",
            "condo_match_score": None,
            "condo_match_evidence": evidence,
            "condo_match_candidates": [],
            "condo_match_updated_at": matched_at,
        }

    postal_code = "".join(char for char in str(row.postal_code or "") if char.isdigit())
    if postal_code:
        postal_matches = [
            building for building in candidates
            if "".join(char for char in str(building.postal_code or "") if char.isdigit()) == postal_code
        ]
        if postal_matches:
            candidates = postal_matches
            evidence.append("postal_code")

    ids = sorted(building.id for building in candidates)
    if len(candidates) != 1:
        return {
            "portal_building_id": None,
            "condo_match_status": "ambiguous",
            "condo_match_score": None,
            "condo_match_evidence": evidence + ["multiple_buildings_same_address"],
            "condo_match_candidates": ids,
            "condo_match_updated_at": matched_at,
        }

    building = candidates[0]
    return {
        "portal_building_id": building.id,
        "condo_match_status": "matched",
        # Ranking points describe exact-address evidence, not probability.
        "condo_match_score": 100 if "postal_code" in evidence else 90,
        "condo_match_evidence": evidence,
        "condo_match_candidates": ids,
        "condo_match_updated_at": matched_at,
    }


def match_itbi_condominiums(db: Session, *, city: str = "belo_horizonte") -> dict[str, int | str]:
    """Match pending ITBI rows to a unique collected building by exact address.

    Duplicate buildings at the same street and number are narrowed by postal
    code when possible. Remaining ties are stored as ambiguous with candidate
    IDs instead of assigning an arbitrary condominium. The ITBI area remains
    untouched; portal unit-area ranges are available through the linked record.
    """
    index = _building_index(db, city)
    if not index:
        return {"city": city, "selected": 0, "matched": 0, "ambiguous": 0, "not_found": 0, "insufficient_address": 0}

    counts = {"selected": 0, "matched": 0, "ambiguous": 0, "not_found": 0, "insufficient_address": 0}
    matched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    last_id = 0
    while True:
        rows = db.execute(
            select(
                Transaction.id,
                Transaction.city,
                Transaction.street,
                Transaction.street_number,
                Transaction.postal_code,
            )
            .where(Transaction.city == city)
            .where(Transaction.condo_match_status.in_(REPROCESS_STATUSES))
            .where(Transaction.id > last_id)
            .order_by(Transaction.id)
            .limit(BATCH_SIZE)
        ).all()
        if not rows:
            break

        updates = []
        for row in rows:
            last_id = row.id
            key = (row.city, street_key(row.street) or "", address_key(row.street_number) or "")
            values = _match_values(row, index.get(key), matched_at=matched_at)
            updates.append({"id": row.id, **values})
            counts["selected"] += 1
            counts[values["condo_match_status"]] += 1

        db.bulk_update_mappings(Transaction, updates)
        db.commit()

    return {"city": city, **counts}
