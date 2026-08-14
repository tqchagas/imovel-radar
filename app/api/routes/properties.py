from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.property_history import PropertyKey, filter_transactions_for_key, key_from_transaction
from app.models.transaction import Transaction
from app.schemas.property import PropertyOut
from app.services.property_data import (
    fetch_building_candidates,
    get_property as load_property,
    to_property_out,
)

router = APIRouter()


@router.get("/properties", response_model=PropertyOut)
def get_property(
    city: str = Query(...),
    street: str = Query(...),
    street_number: str | None = Query(None),
    complement: str | None = Query(None),
    db: Session = Depends(get_db),
) -> PropertyOut:
    result = load_property(db, city, street, street_number, complement)
    if result is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return result


@router.get(
    "/properties/by-transaction/{transaction_id}",
    response_model=PropertyOut,
)
def get_property_by_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
) -> PropertyOut:
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    key = key_from_transaction(tx)
    candidates = fetch_building_candidates(db, key.city, key.street, key.street_number)
    matched = filter_transactions_for_key(candidates, key)
    if not matched:
        # Should not happen if tx exists and matches itself
        matched = [tx]
    return to_property_out(key, matched)
