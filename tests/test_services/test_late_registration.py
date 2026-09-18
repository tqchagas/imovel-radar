from datetime import date

from app.ingestion.base import ParsedTransaction
from app.ingestion.loader import load_transactions
from app.models.transaction import Transaction
from app.services.late_registration import mark_late_registrations
from app.services.market_data import fetch_sales

CASTIGLIANO = [
    ("APT 301", date(2015, 10, 5), 400_000, 145.60),
    ("APT 203", date(2015, 11, 4), 383_000, 99.53),
    ("APT 201", date(2015, 11, 17), 380_000, 98.52),
    ("APT 302", date(2024, 12, 4), 665_000, 145.60),
    ("APT 204", date(2025, 3, 24), 354_000, 97.80),
    # Só marca a cobertura da base: sem uma quitação anterior ao prédio, o
    # lançamento dele não estaria dentro dela.
    ("APT 101", date(2008, 1, 2), 150_000, 60.0, "RUA OUTRA"),
]


def _record(
    complement: str, when: date, value: float, area: float, street: str = "RUA CASTIGLIANO"
) -> ParsedTransaction:
    return ParsedTransaction(
        city="belo_horizonte",
        source_row_hash=f"{street}-{complement}-{when}",
        raw_address=f"{street} 1395 - {complement}",
        street=street,
        street_number="1395",
        complement=complement,
        postal_code=None,
        neighborhood="PRADO",
        construction_year=2015,
        land_area=None,
        built_area_acquired=area,
        acquired_area_total=area,
        finish_standard=None,
        acquired_fraction=0.1,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=value,
        calc_base_value=value,
        zoning=None,
        settlement_date=when,
    )


def _late(db) -> set[str]:
    return {
        t.complement for t in db.query(Transaction).filter(Transaction.late_registration)
    }


def test_ingestion_marks_late_registrations(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])

    assert _late(db_session) == {"APT 204"}


def test_marking_is_recomputed_when_the_building_changes(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])
    # Uma primeira venda do 204 mais antiga aparece: a de 2025 vira revenda.
    load_transactions(db_session, [_record("APT 204", date(2016, 1, 10), 350_000, 97.80)])

    assert _late(db_session) == set()


def test_mark_reports_how_many_are_flagged(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])

    assert mark_late_registrations(db_session, "belo_horizonte") == 1
    assert mark_late_registrations(db_session, "sao_paulo") == 0


def test_market_sales_leave_late_registrations_out(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])

    sales = fetch_sales(db_session, "belo_horizonte", date(2024, 1, 1), date(2025, 12, 31))

    assert [s.declared_value for s in sales] == [665_000]  # 204 de 2025 fica fora
