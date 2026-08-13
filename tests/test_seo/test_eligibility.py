from app.seo.eligibility import PageQuality, neighborhood_quality, property_quality, street_quality


def test_neighborhood_requires_enough_transactions_and_valid_areas() -> None:
    assert neighborhood_quality(30, 10) == PageQuality(indexable=True, reason=None)
    assert neighborhood_quality(29, 10).indexable is False
    assert neighborhood_quality(30, 9).indexable is False


def test_street_requires_transactions_and_distinct_addresses() -> None:
    assert street_quality(20, 5).indexable is True
    assert street_quality(20, 4).reason == "few_addresses"


def test_property_requires_two_settlements() -> None:
    assert property_quality(2).indexable is True
    assert property_quality(1).reason == "few_transactions"
