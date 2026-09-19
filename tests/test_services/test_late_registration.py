from datetime import date

from app.ingestion.base import ParsedTransaction
from app.ingestion.loader import load_transactions
from app.models.transaction import Transaction
from app.services.late_registration import mark_late_registrations
from app.services.market_data import count_late_registrations, fetch_sales

CASTIGLIANO = [
    ("APT 301", date(2015, 10, 5), 400_000, 145.60),
    ("APT 203", date(2015, 11, 4), 383_000, 99.53),
    ("APT 201", date(2015, 11, 17), 380_000, 98.52),
    ("APT 302", date(2024, 12, 4), 665_000, 145.60),
    ("APT 204", date(2025, 3, 24), 354_000, 97.80, 410_760),
    # Só marca a cobertura da base: sem uma quitação anterior ao prédio, o
    # lançamento dele não estaria dentro dela.
    ("APT 101", date(2008, 1, 2), 150_000, 60.0, None, "RUA OUTRA"),
]


def _record(
    complement: str,
    when: date,
    value: float,
    area: float,
    base: float | None = None,
    street: str = "RUA CASTIGLIANO",
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
        calc_base_value=value if base is None else base,
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
    load_transactions(
        db_session, [_record("APT 204", date(2016, 1, 10), 350_000, 97.80, 380_000)]
    )

    assert _late(db_session) == set()


def test_mark_reports_how_many_are_flagged(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])

    resultado = mark_late_registrations(db_session, "belo_horizonte")
    assert (resultado.before, resultado.after) == (1, 1)
    assert resultado.by_confidence == {"media": 1}
    assert resultado.change_ratio == 0.0
    assert mark_late_registrations(db_session, "sao_paulo").after == 0


def test_marking_stored_before_confidence_existed_is_cleared(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])
    # Marca antiga, sem confiança, numa quitação que a regra não marca.
    antiga = db_session.query(Transaction).filter_by(complement="APT 301").one()
    antiga.late_registration = True
    db_session.commit()

    resultado = mark_late_registrations(db_session, "belo_horizonte")

    assert resultado.before == 2
    assert _late(db_session) == {"APT 204"}


def test_market_sales_leave_late_registrations_out(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])

    sales = fetch_sales(db_session, "belo_horizonte", date(2024, 1, 1), date(2025, 12, 31))

    assert [s.declared_value for s in sales] == [665_000]  # 204 de 2025 fica fora


def test_market_data_counts_what_it_left_out(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])

    window = (date(2024, 1, 1), date(2025, 12, 31))
    assert count_late_registrations(db_session, "belo_horizonte", *window) == 1
    assert count_late_registrations(db_session, "belo_horizonte", *window, street="RUA OUTRA") == 0


def test_ingestion_only_recomputes_the_streets_it_touched(db_session) -> None:
    load_transactions(db_session, [_record(*row) for row in CASTIGLIANO])
    # Marca forjada numa rua que a próxima ingestão não toca: tem de sobreviver.
    outra = db_session.query(Transaction).filter_by(street="RUA OUTRA").one()
    outra.late_registration = True
    db_session.commit()

    load_transactions(
        db_session, [_record("APT 205", date(2025, 6, 1), 350_000, 97.80, 410_760)]
    )

    assert _late(db_session) == {"APT 204", "APT 205", "APT 101"}
    # O recálculo da cidade inteira desfaz a marca forjada.
    mark_late_registrations(db_session, "belo_horizonte")
    assert _late(db_session) == {"APT 204", "APT 205"}
