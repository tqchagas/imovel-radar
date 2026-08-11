from datetime import date

from app.domain.curiosities import (
    MIN_REAL_VALUE,
    Settlement,
    fastest_flips,
    neighborhood_spread,
    priciest_per_m2,
    priciest_sales,
    settlements_by_month,
    top_appreciation,
    top_buildings,
    top_units,
)


def sale(
    *,
    street: str = "RUA A",
    number: str | None = "100",
    complement: str | None = "AP 101",
    neighborhood: str = "CENTRO",
    day: date,
    value: float = 500_000.0,
    area: float | None = 80.0,
    fraction: float | None = 1.0,
    construction_type: str | None = "AP",
) -> Settlement:
    return Settlement(
        street=street,
        street_number=number,
        complement=complement,
        neighborhood=neighborhood,
        settlement_date=day,
        declared_value=value,
        built_area_acquired=area,
        acquired_fraction=fraction,
        construction_type=construction_type,
    )


class TestTopBuildings:
    def test_ranks_addresses_by_settlement_count(self):
        sales = [
            sale(street="RUA A", number="100", complement="AP 1", day=date(2020, 1, 1)),
            sale(street="RUA A", number="100", complement="AP 2", day=date(2021, 1, 1)),
            sale(street="RUA A", number="100", complement="AP 3", day=date(2022, 1, 1)),
            sale(street="RUA B", number="200", complement="AP 1", day=date(2022, 6, 1)),
            sale(street="RUA B", number="200", complement="AP 2", day=date(2022, 7, 1)),
        ]

        result = top_buildings(sales)

        assert [s.transaction_count for s in result] == [3, 2]
        assert result[0].street == "RUA A"
        assert result[0].unit_count == 3
        assert result[0].last_settlement_date == date(2022, 1, 1)

    def test_skips_addresses_below_the_minimum(self):
        sales = [sale(day=date(2020, 1, 1))]

        assert top_buildings(sales, min_transactions=2) == []

    def test_counts_units_by_normalized_complement(self):
        sales = [
            sale(complement="AP 902", day=date(2020, 1, 1)),
            sale(complement="apto 902", day=date(2021, 1, 1)),
        ]

        assert top_buildings(sales)[0].unit_count == 1


class TestTopUnits:
    def test_ranks_units_that_changed_hands_the_most(self):
        sales = [
            sale(complement="AP 101", day=date(2015, 1, 1)),
            sale(complement="AP 101", day=date(2018, 1, 1)),
            sale(complement="AP 101", day=date(2021, 1, 1), value=900_000.0),
            sale(complement="AP 202", day=date(2019, 1, 1)),
        ]

        result = top_units(sales)

        assert len(result) == 1
        assert result[0].transaction_count == 3
        assert result[0].first_settlement_date == date(2015, 1, 1)
        assert result[0].last_value == 900_000.0

    def test_treats_complement_spellings_as_one_unit(self):
        sales = [
            sale(complement="AP 902", day=date(2015, 1, 1)),
            sale(complement="apto 902", day=date(2018, 1, 1)),
        ]

        assert top_units(sales)[0].transaction_count == 2

    def test_ignores_the_lot_level_bucket(self):
        """Rows with no complement are many units at one address, not one unit."""
        sales = [
            sale(complement=None, day=date(2015, 1, 1)),
            sale(complement=None, day=date(2018, 1, 1)),
            sale(complement=None, day=date(2021, 1, 1)),
        ]

        assert top_units(sales) == []

    def test_caps_how_many_units_one_address_can_take(self):
        crowded = [
            sale(street="RUA A", complement=f"AP {unit}", day=date(2015 + year, 1, 1))
            for unit in range(5)
            for year in range(4)
        ]
        elsewhere = [
            sale(street="RUA B", complement="AP 1", day=date(2015, 1, 1)),
            sale(street="RUA B", complement="AP 1", day=date(2016, 1, 1)),
        ]

        result = top_units([*crowded, *elsewhere], max_per_building=2)

        assert sum(1 for s in result if s.unit.street == "RUA A") == 2
        assert any(s.unit.street == "RUA B" for s in result)


class TestTopAppreciation:
    def test_reports_total_and_annualized_gain(self):
        sales = [
            sale(day=date(2010, 1, 1), value=200_000.0),
            sale(day=date(2020, 1, 1), value=800_000.0),
        ]

        result = top_appreciation(sales)

        assert len(result) == 1
        assert result[0].total_pct == 300.0
        assert 14.5 < result[0].annualized_pct < 15.5
        assert 9.9 < result[0].years < 10.1

    def test_ignores_symbolic_transfers(self):
        sales = [
            sale(day=date(2010, 1, 1), value=MIN_REAL_VALUE - 1),
            sale(day=date(2020, 1, 1), value=800_000.0),
        ]

        assert top_appreciation(sales) == []

    def test_ignores_pairs_closer_than_the_minimum_span(self):
        sales = [
            sale(day=date(2020, 1, 1), value=200_000.0),
            sale(day=date(2020, 6, 1), value=800_000.0),
        ]

        assert top_appreciation(sales, min_years=1.0) == []

    def test_skips_partial_shares(self):
        sales = [
            sale(day=date(2010, 1, 1), value=200_000.0, fraction=1.0),
            sale(day=date(2015, 1, 1), value=60_000.0, fraction=0.1),
            sale(day=date(2020, 1, 1), value=800_000.0, fraction=1.0),
        ]

        result = top_appreciation(sales)

        assert result[0].from_value == 200_000.0
        assert result[0].to_value == 800_000.0

    def test_skips_pairs_whose_areas_disagree(self):
        """A lot bought before the building went up is not an appreciation."""
        sales = [
            sale(day=date(2010, 1, 1), value=80_000.0, area=300.0),
            sale(day=date(2020, 1, 1), value=2_000_000.0, area=90.0),
        ]

        assert top_appreciation(sales) == []

    def test_ignores_the_lot_level_bucket(self):
        sales = [
            sale(complement=None, day=date(2010, 1, 1), value=200_000.0),
            sale(complement=None, day=date(2020, 1, 1), value=800_000.0),
        ]

        assert top_appreciation(sales) == []

    def test_skips_first_sales_far_below_the_neighborhood(self):
        """An off-plan price is a real settlement, not a market price."""
        market = [
            sale(complement=f"AP {n}", day=date(2010, 6, 1), value=800_000.0)
            for n in range(6)
        ]
        off_plan = [
            sale(complement="AP 99", day=date(2010, 1, 1), value=60_000.0),
            sale(complement="AP 99", day=date(2020, 1, 1), value=900_000.0),
        ]

        assert top_appreciation([*market, *off_plan]) == []

    def test_keeps_pairs_priced_at_the_market(self):
        market = [
            sale(complement=f"AP {n}", day=date(2010, 6, 1), value=800_000.0)
            for n in range(6)
        ]
        real = [
            sale(complement="AP 99", day=date(2010, 1, 1), value=700_000.0),
            sale(complement="AP 99", day=date(2020, 1, 1), value=1_400_000.0),
        ]

        result = top_appreciation([*market, *real])

        assert len(result) == 1
        assert result[0].total_pct == 100.0


class TestFastestFlips:
    def test_ranks_by_shortest_gap_between_full_sales(self):
        sales = [
            sale(complement="AP 1", day=date(2020, 1, 1), value=400_000.0),
            sale(complement="AP 1", day=date(2020, 3, 1), value=500_000.0),
            sale(complement="AP 2", day=date(2020, 1, 1), value=400_000.0),
            sale(complement="AP 2", day=date(2023, 1, 1), value=500_000.0),
        ]

        result = fastest_flips(sales)

        assert result[0].days == 60
        assert result[0].delta_pct == 25.0
        assert result[1].days == 1096

    def test_drops_pairs_inside_a_week(self):
        """Days apart is registry mechanics, not somebody reselling."""
        sales = [
            sale(day=date(2020, 1, 1), value=400_000.0),
            sale(day=date(2020, 1, 3), value=3_000_000.0),
        ]

        assert fastest_flips(sales) == []

    def test_drops_pairs_whose_areas_disagree(self):
        sales = [
            sale(day=date(2020, 1, 1), value=400_000.0, area=300.0),
            sale(day=date(2020, 6, 1), value=3_000_000.0, area=90.0),
        ]

        assert fastest_flips(sales) == []


class TestRecords:
    def test_priciest_sales_sorts_by_declared_value(self):
        sales = [
            sale(day=date(2020, 1, 1), value=1_000_000.0),
            sale(day=date(2021, 1, 1), value=3_000_000.0),
        ]

        assert priciest_sales(sales)[0].declared_value == 3_000_000.0

    def test_priciest_per_m2_ignores_tiny_areas(self):
        sales = [
            sale(day=date(2020, 1, 1), value=300_000.0, area=10.0),
            sale(day=date(2021, 1, 1), value=1_000_000.0, area=100.0),
        ]

        result = priciest_per_m2(sales)

        assert len(result) == 1
        assert result[0].price_per_m2 == 10_000.0

    def test_priciest_per_m2_drops_rows_far_above_the_city(self):
        """R$ 300k/m² is a value covering more area than the row declares."""
        normal = [
            sale(day=date(2020, 1, 1), value=1_000_000.0, area=100.0) for _ in range(9)
        ]
        artifact = sale(day=date(2021, 1, 1), value=15_000_000.0, area=50.0)

        result = priciest_per_m2([*normal, artifact])

        assert all(record.price_per_m2 == 10_000.0 for record in result)


class TestByMonth:
    def test_counts_settlements_per_month_oldest_first(self):
        sales = [
            sale(day=date(2021, 3, 5)),
            sale(day=date(2021, 3, 20)),
            sale(day=date(2020, 12, 1)),
        ]

        result = settlements_by_month(sales)

        assert [(m.year, m.month, m.transaction_count) for m in result] == [
            (2020, 12, 1),
            (2021, 3, 2),
        ]


class TestNeighborhoodSpread:
    def test_ranks_by_p75_over_p25(self):
        wide = [
            sale(neighborhood="WIDE", day=date(2024, 6, 1), value=float(v))
            for v in list(range(100_000, 200_000, 25_000))
            + list(range(1_000_000, 2_000_000, 250_000))
        ]
        tight = [
            sale(neighborhood="TIGHT", day=date(2024, 6, 1), value=float(v))
            for v in range(500_000, 508_000, 1_000)
        ]

        result = neighborhood_spread(
            wide + tight, reference=date(2024, 12, 31), min_transactions=4
        )

        assert result[0].neighborhood == "WIDE"
        assert result[0].spread_ratio > result[1].spread_ratio

    def test_skips_neighborhoods_below_the_minimum(self):
        sales = [sale(neighborhood="TINY", day=date(2024, 6, 1))]

        assert neighborhood_spread(sales, reference=date(2024, 12, 31)) == []

    def test_only_looks_at_the_window(self):
        sales = [
            sale(neighborhood="OLD", day=date(2015, 1, 1), value=float(v))
            for v in range(100_000, 600_000, 100_000)
        ]

        assert neighborhood_spread(
            sales, reference=date(2024, 12, 31), min_transactions=4
        ) == []
