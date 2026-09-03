from datetime import date
from io import TextIOWrapper

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.slugs import address_key
from app.ingestion.belo_horizonte import CITY as BELO_HORIZONTE_CITY
from app.ingestion.belo_horizonte import parse_stream as parse_belo_horizonte
from app.ingestion.loader import load_transactions
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionList, TransactionOut, UploadResult

router = APIRouter()

# R$/m² of a row; nullif keeps zero-area rows out of the division.
_PRICE_PER_M2 = Transaction.declared_value / func.nullif(
    Transaction.built_area_acquired, 0
)

SORTS = {
    "date_desc": Transaction.settlement_date.desc(),
    "date_asc": Transaction.settlement_date.asc(),
    "value_desc": Transaction.declared_value.desc(),
    "value_asc": Transaction.declared_value.asc(),
    "m2_desc": _PRICE_PER_M2.desc().nullslast(),
    "m2_asc": _PRICE_PER_M2.asc().nullslast(),
}


@router.get("/transactions", response_model=TransactionList)
def list_transactions(
    city: str | None = None,
    neighborhood: str | None = None,
    street: str | None = None,
    street_number: str | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_area: float | None = None,
    max_area: float | None = None,
    construction_type: str | None = None,
    occupation_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = Query("date_desc"),
    limit: int = Query(50, le=200, gt=0),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> TransactionList:
    if sort not in SORTS:
        raise HTTPException(
            status_code=400, detail=f"Unknown sort '{sort}'. Available: {list(SORTS)}"
        )
    stmt = select(Transaction)
    if city:
        stmt = stmt.where(Transaction.city == city)
    if neighborhood:
        stmt = stmt.where(Transaction.neighborhood == neighborhood)
    if street:
        stmt = stmt.where(Transaction.street.ilike(f"%{street}%"))
    if street_number:
        stmt = stmt.where(Transaction.street_number == street_number)
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
        # id breaks ties so paging stays stable across requests.
        stmt.order_by(SORTS[sort], Transaction.id.desc()).limit(limit).offset(offset)
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
    # A cidade é gravada normalizada ("belo_horizonte"); quem chama manda o nome
    # como se escreve. Sem converter, a lista voltava vazia e todo seletor de
    # bairro da interface nascia sem opção nenhuma.
    stmt = (
        select(Transaction.neighborhood)
        .distinct()
        .where(Transaction.city == address_key(city))
        .order_by(Transaction.neighborhood)
    )
    return list(db.scalars(stmt))


ADAPTERS = {
    BELO_HORIZONTE_CITY: parse_belo_horizonte,
}


@router.post("/upload", response_model=UploadResult, include_in_schema=False)
def upload_itbi_file(
    city: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadResult:
    if city not in ADAPTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown city '{city}'. Available: {list(ADAPTERS)}",
        )

    text_file = TextIOWrapper(file.file, encoding="utf-8-sig")
    try:
        records = list(ADAPTERS[city](text_file))
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    inserted = load_transactions(db, records)
    return UploadResult(city=city, inserted=inserted, total_rows=len(records))
