from collections.abc import Iterable, Iterator

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.ingestion.base import ParsedTransaction
from app.models.transaction import Transaction

# Postgres refuses a statement with more than 65535 bind parameters. An 80MB
# ITBI export is ~450k rows, so both the "which hashes are already stored"
# lookup and the insert have to be split: a single statement covering the whole
# file kills the connection (OperationalError) before any row lands.
HASH_LOOKUP_CHUNK = 10_000
# ~21 columns per row, so 1000 rows stays far below the parameter ceiling.
INSERT_CHUNK = 1_000


def _chunks[T](items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def load_transactions(db: Session, records: Iterable[ParsedTransaction]) -> int:
    # The same file can carry a row twice; keeping the first occurrence avoids a
    # unique violation inside a single insert chunk.
    unique = {r.source_row_hash: r for r in records}

    existing: set[str] = set()
    for chunk in _chunks(list(unique), HASH_LOOKUP_CHUNK):
        existing.update(
            db.scalars(
                select(Transaction.source_row_hash).where(
                    Transaction.source_row_hash.in_(chunk)
                )
            )
        )

    new_rows = [r.__dict__ for h, r in unique.items() if h not in existing]
    for chunk in _chunks(new_rows, INSERT_CHUNK):
        db.execute(insert(Transaction), chunk)
    db.commit()
    return len(new_rows)
