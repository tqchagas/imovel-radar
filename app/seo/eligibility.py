"""Indexation rules that keep low-information pages out of search results."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PageQuality:
    indexable: bool
    reason: str | None


def neighborhood_quality(transaction_count: int, valid_area_count: int) -> PageQuality:
    if transaction_count < 30:
        return PageQuality(False, "few_transactions")
    if valid_area_count < 10:
        return PageQuality(False, "few_valid_areas")
    return PageQuality(True, None)


def street_quality(transaction_count: int, property_count: int) -> PageQuality:
    if transaction_count < 20:
        return PageQuality(False, "few_transactions")
    if property_count < 5:
        return PageQuality(False, "few_addresses")
    return PageQuality(True, None)


def property_quality(transaction_count: int) -> PageQuality:
    if transaction_count < 2:
        return PageQuality(False, "few_transactions")
    return PageQuality(True, None)
