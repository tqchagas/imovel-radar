from datetime import date

from pydantic import BaseModel


class OverviewOut(BaseModel):
    city: str | None
    transaction_count: int
    neighborhood_count: int
    year_from: int | None
    year_to: int | None
    last_settlement_date: date | None


class NeighborhoodStatOut(BaseModel):
    neighborhood: str
    transaction_count: int
    median_price_per_m2: float | None
    delta_pct: float | None


class NeighborhoodRankingOut(BaseModel):
    city: str | None
    months: int
    reference_date: date | None
    items: list[NeighborhoodStatOut]


class TypeStatOut(BaseModel):
    construction_type: str | None
    label: str
    description: str | None
    transaction_count: int
    median_price_per_m2: float | None


class StreetStatOut(BaseModel):
    street: str
    transaction_count: int
    median_price_per_m2: float | None


class StreetAddressStatOut(BaseModel):
    street_number: str
    transaction_count: int
    median_price_per_m2: float | None
    last_settlement_date: date


class StreetDetailOut(BaseModel):
    city: str
    street: str
    months: int
    reference_date: date
    transaction_count: int
    property_count: int
    median_ticket: float | None
    p25_ticket: float | None
    p75_ticket: float | None
    median_area: float | None
    median_price_per_m2: float | None
    top_addresses: list[StreetAddressStatOut]


class NeighborhoodDetailOut(BaseModel):
    city: str
    neighborhood: str
    months: int
    reference_date: date | None
    transaction_count: int
    residential_share_pct: float | None
    median_price_per_m2: float | None
    delta_pct: float | None
    median_ticket: float | None
    p25_ticket: float | None
    p75_ticket: float | None
    median_area: float | None
    per_month: float | None
    by_construction_type: list[TypeStatOut]
    top_streets: list[StreetStatOut]
