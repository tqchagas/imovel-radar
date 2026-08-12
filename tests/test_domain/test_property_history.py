from datetime import date
from types import SimpleNamespace

from app.domain.property_history import (
    PropertyKey,
    build_summary,
    build_timeline,
    filter_transactions_for_key,
)


def _tx(**kwargs):
    defaults = dict(
        id=1,
        city="belo_horizonte",
        street="AVE AUGUSTO DE LIMA",
        street_number="134",
        complement="APT 1201",
        declared_value=270000.0,
        calc_base_value=270000.0,
        built_area_acquired=47.25,
        acquired_fraction=0.00333,
        settlement_date=date(2020, 1, 1),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_filter_groups_normalized_complements() -> None:
    key = PropertyKey(
        city="belo_horizonte",
        street="AVE AUGUSTO DE LIMA",
        street_number="134",
        complement="APTO 1201",
    )
    txs = [
        _tx(id=1, complement="APT 1201", settlement_date=date(2020, 1, 1)),
        _tx(id=2, complement="AP 1201", settlement_date=date(2022, 6, 1)),
        _tx(id=3, complement="APT 999", settlement_date=date(2021, 1, 1)),
        _tx(id=4, complement="LJ 1201", settlement_date=date(2023, 1, 1)),
    ]
    matched = filter_transactions_for_key(txs, key)
    assert [t.id for t in matched] == [1, 2]


def test_filter_matches_street_and_complement_slugs() -> None:
    key = PropertyKey(
        city="belo-horizonte",
        street="ave-augusto-de-lima",
        street_number="134",
        complement="apt-1201",
    )
    txs = [
        _tx(id=1, complement="APT 1201", settlement_date=date(2020, 1, 1)),
        _tx(id=2, complement="APTO 1201", settlement_date=date(2022, 6, 1)),
        _tx(id=3, complement="APT 999", settlement_date=date(2021, 1, 1)),
    ]
    matched = filter_transactions_for_key(txs, key)
    assert [t.id for t in matched] == [1, 2]


def test_lot_level_excludes_units_with_complement() -> None:
    key = PropertyKey(
        city="belo_horizonte",
        street="RUA A",
        street_number="1",
        complement=None,
    )
    txs = [
        _tx(id=1, street="RUA A", street_number="1", complement=None),
        _tx(id=2, street="RUA A", street_number="1", complement="APT 1"),
    ]
    matched = filter_transactions_for_key(txs, key)
    assert [t.id for t in matched] == [1]


def test_summary_appreciation_only_between_full_fraction_sales() -> None:
    # Same ideal fraction = full unit sales; one half-fraction = cota
    txs = [
        _tx(
            id=1,
            declared_value=200000.0,
            acquired_fraction=0.003,
            settlement_date=date(2018, 1, 1),
        ),
        _tx(
            id=2,
            declared_value=50000.0,
            acquired_fraction=0.0015,  # half cota
            settlement_date=date(2019, 1, 1),
        ),
        _tx(
            id=3,
            declared_value=300000.0,
            acquired_fraction=0.003,
            settlement_date=date(2022, 1, 1),
        ),
    ]
    summary = build_summary(txs)
    assert summary.transaction_count == 3
    assert summary.last_sale_value == 300000.0
    # Appreciation: 200k -> 300k full sales only = +50%
    assert summary.appreciation_pct == 50.0


def test_timeline_marks_partial_and_base_gap() -> None:
    txs = [
        _tx(
            id=1,
            declared_value=200000.0,
            calc_base_value=200000.0,
            acquired_fraction=0.003,
            built_area_acquired=50.0,
            settlement_date=date(2018, 1, 1),
        ),
        _tx(
            id=2,
            declared_value=80000.0,
            calc_base_value=100000.0,
            acquired_fraction=0.0015,
            built_area_acquired=50.0,
            settlement_date=date(2019, 1, 1),
        ),
    ]
    points = build_timeline(txs)
    assert points[0].is_partial is False
    assert points[1].is_partial is True
    assert "cota_parcial" in points[1].markers
    assert points[1].calc_base_gap_pct == 25.0
