from datetime import date

from app.domain.late_registration import Settlement, flag_late_registrations

COVERAGE_START = date(2008, 1, 2)


def _flagged(sales) -> set[int]:
    return set(flag_late_registrations(sales, coverage_start=COVERAGE_START))


def _s(
    id: int, complement: str, when: date, value: float, area: float, base: float | None = None, **kwargs
) -> Settlement:
    fields = dict(
        id=id,
        street="RUA CASTIGLIANO",
        street_number="1395",
        complement=complement,
        settlement_date=when,
        declared_value=value,
        calc_base_value=value if base is None else base,
        built_area_acquired=area,
        construction_year=2015,
        construction_type="AP",
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
        _s(4, "APT 302", date(2018, 1, 24), 340_000, 145.60, base=506_688),
        _s(5, "APT 304", date(2018, 2, 27), 445_000, 145.60, base=506_688),
        _s(6, "APT 303", date(2018, 4, 9), 300_000, 145.60, base=506_688),
        _s(7, "APT 302", date(2024, 12, 4), 665_000, 145.60),
        _s(8, "APT 204", date(2025, 3, 24), 354_000, 97.80, base=410_760),
    ]


def test_marks_first_sales_at_launch_price_years_later() -> None:
    assert _flagged(_castigliano()) == {4, 5, 6, 8}


def test_resale_is_never_marked() -> None:
    flagged = _flagged(_castigliano())
    assert 7 not in flagged


def test_complement_spelling_does_not_split_the_unit() -> None:
    sales = _castigliano() + [_s(9, "APTO 302", date(2026, 1, 10), 300_000, 145.60, base=700_000)]
    assert 9 not in _flagged(sales)


def test_first_sale_at_market_price_is_not_marked() -> None:
    sales = _castigliano()[:3] + [_s(4, "APT 204", date(2025, 3, 24), 520_000, 97.80)]
    assert _flagged(sales) == set()


def test_first_sale_soon_after_launch_is_not_marked() -> None:
    sales = _castigliano()[:3] + [_s(4, "APT 204", date(2016, 6, 1), 354_000, 97.80, base=410_760)]
    assert _flagged(sales) == set()


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
    assert _flagged(sales) == set()


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
    assert _flagged(sales) == set()


def test_needs_enough_launch_sales_to_set_the_price() -> None:
    sales = _castigliano()[:2] + [_s(8, "APT 204", date(2025, 3, 24), 354_000, 97.80, base=410_760)]
    assert _flagged(sales) == set()


def test_sales_without_unit_are_ignored() -> None:
    sales = _castigliano() + [_s(9, None, date(2025, 1, 1), 100_000, 100)]
    assert 9 not in _flagged(sales)


def test_first_sale_declared_at_the_city_valuation_is_not_marked() -> None:
    # Declarado igual à base: a prefeitura concorda que é preço de hoje, e é
    # estoque da construtora vendido tarde, não contrato antigo.
    sales = _castigliano()[:3] + [_s(8, "APT 204", date(2025, 3, 24), 354_000, 97.80)]
    assert _flagged(sales) == set()


def test_units_are_compared_within_their_construction_type() -> None:
    # Salas de lançamento a R$ 2 mil/m² não fazem de um apartamento a R$ 3,6
    # mil/m² um contrato antigo: só apartamento mede apartamento.
    salas = [
        _s(20 + i, f"SALA {i}", date(2015, 10, 1), 60_000, 30.0, construction_type="SL")
        for i in range(3)
    ]
    sales = salas + [_s(8, "APT 204", date(2025, 3, 24), 354_000, 97.80, base=410_760)]
    assert _flagged(sales) == set()


def test_parking_spaces_are_never_marked() -> None:
    vagas = [
        _s(20 + i, f"GA {i}", date(2015, 10, 1), 20_000, 12.0, construction_type="VC")
        for i in range(3)
    ]
    late = _s(30, "GA 9", date(2020, 1, 1), 15_000, 12.0, base=40_000, construction_type="VC")
    assert _flagged(vagas + [late]) == set()


def _resale(id: int, complement: str, when: date, price_per_m2: float) -> Settlement:
    # Revenda: a unidade já teve a primeira quitação no lançamento.
    return _s(id, complement, when, price_per_m2 * 100, 100.0)


def _with_resales(first_sale_price_m2: float) -> list[Settlement]:
    lancamento = [
        _s(1, "APT 101", date(2015, 10, 1), 380_000, 100.0),
        _s(2, "APT 102", date(2015, 11, 1), 380_000, 100.0),
        _s(3, "APT 103", date(2015, 12, 1), 380_000, 100.0),
    ]
    revendas = [
        _resale(10, "APT 101", date(2021, 3, 1), 4_000),
        _resale(11, "APT 102", date(2021, 9, 1), 4_200),
    ]
    tardia = _s(
        20, "APT 204", date(2021, 6, 1), first_sale_price_m2 * 100, 100.0, base=500_000
    )
    return lancamento + revendas + [tardia]


def test_launch_price_and_below_resales_is_high_confidence() -> None:
    # Revendas a R$ 4.100/m² na mediana: 3.500 fica abaixo de 0,9x delas e do
    # teto do lançamento (1,1x 3.800).
    flagged = flag_late_registrations(_with_resales(3_500), coverage_start=COVERAGE_START)
    assert flagged == {20: "alta"}


def test_first_sale_at_resale_price_is_not_marked_even_at_launch_price() -> None:
    # R$ 3.800/m² passa no teto do lançamento, mas está a 0,93x das revendas do
    # prédio naquele ano: é o preço de mercado de um mercado que não subiu.
    assert _flagged(_with_resales(3_800)) == set()


def test_resales_alone_mark_with_medium_confidence() -> None:
    # Só duas vendas no lançamento: sem preço de lançamento, as revendas julgam.
    sales = [s for s in _with_resales(3_000) if s.id != 3]
    assert flag_late_registrations(sales, coverage_start=COVERAGE_START) == {20: "media"}


def test_launch_alone_marks_with_medium_confidence() -> None:
    flagged = flag_late_registrations(_castigliano(), coverage_start=COVERAGE_START)
    assert flagged[8] == "media"
