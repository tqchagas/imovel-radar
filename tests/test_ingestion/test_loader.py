from datetime import date

from app.ingestion import loader
from app.ingestion.base import ParsedTransaction
from app.ingestion.loader import load_transactions
from app.models.transaction import Transaction


def _record(hash_suffix: str) -> ParsedTransaction:
    return ParsedTransaction(
        city="belo_horizonte",
        source_row_hash=f"hash-{hash_suffix}",
        raw_address="RUA TESTE 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG",
        street="RUA TESTE",
        street_number="1",
        complement=None,
        postal_code="30000-000",
        neighborhood="CENTRO",
        construction_year=2000,
        land_area=100.0,
        built_area_acquired=80.0,
        acquired_area_total=80.0,
        finish_standard="P3",
        acquired_fraction=1.0,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=200000.0,
        calc_base_value=200000.0,
        zoning="ZA",
        settlement_date=date(2026, 6, 1),
    )


def test_load_transactions_inserts_new_records(db_session) -> None:
    inserted = load_transactions(db_session, [_record("a"), _record("b")])

    assert inserted == 2
    assert db_session.query(Transaction).count() == 2


def test_load_transactions_splits_batches_larger_than_a_chunk(
    db_session, monkeypatch
) -> None:
    monkeypatch.setattr(loader, "HASH_LOOKUP_CHUNK", 3)
    monkeypatch.setattr(loader, "INSERT_CHUNK", 2)
    records = [_record(str(i)) for i in range(11)]

    inserted = load_transactions(db_session, records)

    assert inserted == 11
    assert db_session.query(Transaction).count() == 11


def test_load_transactions_ignores_duplicate_hashes_inside_one_file(
    db_session,
) -> None:
    inserted = load_transactions(db_session, [_record("a"), _record("a")])

    assert inserted == 1
    assert db_session.query(Transaction).count() == 1


def test_load_transactions_is_idempotent_on_rerun(db_session) -> None:
    records = [_record("a"), _record("b")]

    first_run = load_transactions(db_session, records)
    second_run = load_transactions(db_session, records)

    assert first_run == 2
    assert second_run == 0
    assert db_session.query(Transaction).count() == 2
