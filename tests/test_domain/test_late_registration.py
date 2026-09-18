from datetime import date

from app.domain.late_registration import Settlement, flag_late_registrations

COVERAGE_START = date(2008, 1, 2)


def _s(id: int, complement: str, when: date, value: float, area: float, **kwargs) -> Settlement:
    fields = dict(
        id=id,
        street="RUA CASTIGLIANO",
        street_number="1395",
        complement=complement,
        settlement_date=when,
        declared_value=value,
        built_area_acquired=area,
        construction_year=2015,
    )
    fields.update(kwargs)
    return Settlement(**fields)


def _castigliano() -> list[Settlement]:
    # O caso real que motivou a marcação: lançamento em 2015, contratos da
    # planta quitados em 2018 e 2025, uma revenda de verdade em 2024.
    return [
        _s(1, "APT 301", date(2015, 10, 5), 400_000, 145.60),
        _s(2, "APT 203", date(2015, 11, 4), 383_000, 99.53),
        _s(3, "APT 201", date(2015, 11, 17), 380_000, 98.52),
        _s(4, "APT 302", date(2018, 1, 24), 340_000, 145.60),
        _s(5, "APT 304", date(2018, 2, 27), 445_000, 145.60),
        _s(6, "APT 303", date(2018, 4, 9), 300_000, 145.60),
        _s(7, "APT 302", date(2024, 12, 4), 665_000, 145.60),
        _s(8, "APT 204", date(2025, 3, 24), 354_000, 97.80),
    ]


def test_marks_first_sales_at_launch_price_years_later() -> None:
    assert flag_late_registrations(_castigliano(), coverage_start=COVERAGE_START) == {4, 5, 6, 8}


def test_resale_is_never_marked() -> None:
    flagged = flag_late_registrations(_castigliano(), coverage_start=COVERAGE_START)
    assert 7 not in flagged


def test_complement_spelling_does_not_split_the_unit() -> None:
    sales = _castigliano() + [_s(9, "APTO 302", date(2026, 1, 10), 300_000, 145.60)]
    assert 9 not in flag_late_registrations(sales, coverage_start=COVERAGE_START)


def test_first_sale_at_market_price_is_not_marked() -> None:
    sales = _castigliano()[:3] + [_s(4, "APT 204", date(2025, 3, 24), 520_000, 97.80)]
    assert flag_late_registrations(sales, coverage_start=COVERAGE_START) == set()


def test_first_sale_soon_after_launch_is_not_marked() -> None:
    sales = _castigliano()[:3] + [_s(4, "APT 204", date(2016, 6, 1), 354_000, 97.80)]
    assert flag_late_registrations(sales, coverage_start=COVERAGE_START) == set()


def test_building_launched_before_coverage_is_skipped() -> None:
    # Prédio de 2005: a primeira quitação vista em 2008 já é revenda, e a
    # "primeira venda" de outra unidade em 2012 também.
    sales = [
        _s(i, c, d, v, a, construction_year=2005)
        for i, c, d, v, a in [
            (1, "APT 101", date(2008, 3, 1), 300_000, 100),
            (2, "APT 102", date(2008, 5, 1), 300_000, 100),
            (3, "APT 103", date(2008, 7, 1), 300_000, 100),
            (4, "APT 104", date(2012, 1, 1), 300_000, 100),
        ]
    ]
    assert flag_late_registrations(sales, coverage_start=COVERAGE_START) == set()


def test_first_observed_sale_far_from_construction_is_not_a_launch() -> None:
    sales = [
        _s(i, c, d, v, a, construction_year=2010)
        for i, c, d, v, a in [
            (1, "APT 101", date(2016, 3, 1), 300_000, 100),
            (2, "APT 102", date(2016, 5, 1), 300_000, 100),
            (3, "APT 103", date(2016, 7, 1), 300_000, 100),
            (4, "APT 104", date(2020, 1, 1), 300_000, 100),
        ]
    ]
    assert flag_late_registrations(sales, coverage_start=COVERAGE_START) == set()


def test_needs_enough_launch_sales_to_set_the_price() -> None:
    sales = _castigliano()[:2] + [_s(8, "APT 204", date(2025, 3, 24), 354_000, 97.80)]
    assert flag_late_registrations(sales, coverage_start=COVERAGE_START) == set()


def test_sales_without_unit_are_ignored() -> None:
    sales = _castigliano() + [_s(9, None, date(2025, 1, 1), 100_000, 100)]
    assert 9 not in flag_late_registrations(sales, coverage_start=COVERAGE_START)
