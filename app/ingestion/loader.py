from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.base import ParsedTransaction
from app.models.transaction import Transaction


def load_transactions(db: Session, records: Iterable[ParsedTransaction]) -> int:
    records = list(records)
    hashes = [r.source_row_hash for r in records]

    existing = set(
        db.scalars(
            select(Transaction.source_row_hash).where(
                Transaction.source_row_hash.in_(hashes)
            )
        )
    )

    new_rows = [
        Transaction(**r.__dict__)
        for r in records
        if r.source_row_hash not in existing
    ]
    db.add_all(new_rows)
    db.commit()
    return len(new_rows)
