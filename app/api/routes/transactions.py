from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionList, TransactionOut

router = APIRouter()


@router.get("/transactions", response_model=TransactionList)
def list_transactions(
    city: str | None = None,
    neighborhood: str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    construction_type: str | None = None,
    occupation_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(50, le=200, gt=0),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> TransactionList:
    stmt = select(Transaction)
    if city:
        stmt = stmt.where(Transaction.city == city)
    if neighborhood:
        stmt = stmt.where(Transaction.neighborhood == neighborhood)
    if min_value is not None:
        stmt = stmt.where(Transaction.declared_value >= min_value)
    if max_value is not None:
        stmt = stmt.where(Transaction.declared_value <= max_value)
    if min_area is not None:
        stmt = stmt.where(Transaction.built_area_acquired >= min_area)
    if max_area is not None:
        stmt = stmt.where(Transaction.built_area_acquired <= max_area)
    if construction_type:
        stmt = stmt.where(Transaction.construction_type == construction_type)
    if occupation_type:
        stmt = stmt.where(Transaction.occupation_type == occupation_type)
    if date_from is not None:
        stmt = stmt.where(Transaction.settlement_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.settlement_date <= date_to)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(Transaction.settlement_date.desc()).limit(limit).offset(offset)
    ).all()
    return TransactionList(
        total=total, items=[TransactionOut.model_validate(i) for i in items]
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)) -> Transaction:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@router.get("/cities", response_model=list[str])
def list_cities(db: Session = Depends(get_db)) -> list[str]:
    return list(db.scalars(select(Transaction.city).distinct()))


@router.get("/neighborhoods", response_model=list[str])
def list_neighborhoods(city: str, db: Session = Depends(get_db)) -> list[str]:
    stmt = select(Transaction.neighborhood).distinct().where(Transaction.city == city)
    return list(db.scalars(stmt))
