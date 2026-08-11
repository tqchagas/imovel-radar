from datetime import date

from app.domain.market_stats import (
    Sale,
    neighborhood_detail,
    neighborhood_ranking,
    price_per_m2,
    shift_months,
)


def sale(
    *,
    neighborhood: str = "SAVASSI",
    street: str = "RUA A",
    day: date = date(2025, 3, 1),
    value: float = 1_000_000.0,
    area: float | None = 100.0,
    construction_type: str | None = "AP",
    occupation_type: str | None = "RESIDENCIAL",
) -> Sale:
    return Sale(
        neighborhood=neighborhood,
        street=street,
        settlement_date=day,
        declared_value=value,
        built_area_acquired=area,
        construction_type=construction_type,
        occupation_type=occupation_type,
    )


def test_shift_months_clamps_to_shorter_month() -> None:
    assert shift_months(date(2025, 3, 31), 1) == date(2025, 2, 28)
    assert shift_months(date(2025, 1, 15), 12) == date(2024, 1, 15)


def test_price_per_m2_ignores_missing_or_zero_area() -> None:
    assert price_per_m2(sale(value=500_000, area=50)) == 10_000
    assert price_per_m2(sale(area=None)) is None
    assert price_per_m2(sale(area=0)) is None


def test_ranking_sorts_by_median_and_compares_windows() -> None:
    reference = date(2025, 6, 30)
    sales = [
        # Savassi, janela atual: mediana 10.000
        sale(day=date(2025, 6, 1), value=1_000_000, area=100),
        sale(day=date(2025, 5, 1), value=1_000_000, area=100),
        # Savassi, janela anterior: mediana 8.000
        sale(day=date(2024, 6, 1), value=800_000, area=100),
        # Lourdes, janela atual: mediana 12.000
        sale(neighborhood="LOURDES", day=date(2025, 4, 1), value=1_200_000, area=100),
    ]

    ranking = neighborhood_ranking(sales, reference=reference, months=12)

    assert [r.neighborhood for r in ranking] == ["LOURDES", "SAVASSI"]
    savassi = ranking[1]
    assert savassi.transaction_count == 2
    assert savassi.median_price_per_m2 == 10_000
    assert savassi.delta_pct == 25.0
    # Sem janela anterior não há variação a informar.
    assert ranking[0].delta_pct is None


def test_ranking_honours_min_transactions() -> None:
    sales = [sale(day=date(2025, 6, 1))]
    assert neighborhood_ranking(sales, reference=date(2025, 6, 30), min_transactions=2) == []


def test_detail_computes_percentiles_types_and_streets() -> None:
    reference = date(2025, 6, 30)
    sales = [
        sale(day=date(2025, 6, 1), value=400_000, area=50, street="RUA A"),
        sale(day=date(2025, 5, 1), value=800_000, area=80, street="RUA A"),
        sale(day=date(2025, 4, 1), value=1_200_000, area=100, street="RUA B"),
        sale(
            day=date(2025, 3, 1),
            value=200_000,
            area=20,
            street="RUA B",
            construction_type="LO",
            occupation_type="COMERCIAL",
        ),
    ]

    detail = neighborhood_detail(sales, neighborhood="SAVASSI", reference=reference, months=12)

    assert detail.transaction_count == 4
    assert detail.residential_share_pct == 75.0
    assert detail.median_ticket == 600_000
    assert detail.p25_ticket == 350_000
    assert detail.p75_ticket == 900_000
    assert detail.median_area == 65
    assert detail.per_month == 4 / 12

    types = {t.construction_type: t for t in detail.by_construction_type}
    assert types["LO"].median_price_per_m2 == 10_000
    assert types["AP"].transaction_count == 3

    streets = {s.street: s for s in detail.top_streets}
    assert streets["RUA B"].median_price_per_m2 == 11_000
    assert streets["RUA A"].transaction_count == 2


def test_detail_skips_streets_below_minimum() -> None:
    detail = neighborhood_detail(
        [sale(day=date(2025, 6, 1), street="RUA UNICA")],
        neighborhood="SAVASSI",
        reference=date(2025, 6, 30),
    )
    assert detail.top_streets == []
