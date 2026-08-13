from datetime import date

from app.domain.market_stats import Sale
from app.domain.street_stats import street_detail


def _sale(
    street: str,
    value: float,
    area: float | None,
    when: date,
    number: str,
) -> Sale:
    return Sale(
        neighborhood="SAVASSI",
        street=street,
        settlement_date=when,
        declared_value=value,
        built_area_acquired=area,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        street_number=number,
    )


def test_street_detail_summarizes_ticket_area_and_distinct_addresses() -> None:
    sales = [
        _sale("RUA A", 100_000, 50, date(2025, 1, 1), "10"),
        _sale("RUA A", 200_000, 100, date(2025, 2, 1), "20"),
        _sale("RUA A", 300_000, None, date(2025, 3, 1), "10"),
        _sale("RUA A", 50_000, 50, date(2023, 1, 1), "30"),
        _sale("RUA B", 999_000, 100, date(2025, 3, 1), "1"),
    ]

    result = street_detail(sales, street="RUA A", reference=date(2025, 3, 1), months=12)

    assert result.transaction_count == 3
    assert result.property_count == 2
    assert result.median_ticket == 200_000
    assert result.median_price_per_m2 == 2_000
    assert result.median_area == 75
    assert result.top_addresses[0].street_number == "10"
