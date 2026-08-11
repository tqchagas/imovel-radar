from datetime import date

from pydantic import BaseModel, ConfigDict

from app.schemas.transaction import TransactionOut


class TimelinePointOut(BaseModel):
    transaction_id: int
    settlement_date: date
    declared_value: float
    calc_base_value: float
    calc_base_gap_pct: float | None
    built_area_acquired: float | None
    price_per_m2: float | None
    acquired_fraction: float | None
    is_partial: bool
    area_divergent: bool
    markers: list[str]


class PropertySummaryOut(BaseModel):
    last_sale_date: date | None
    last_sale_value: float | None
    appreciation_pct: float | None
    last_price_per_m2: float | None
    price_per_m2_delta_pct: float | None
    transaction_count: int
    year_from: int | None
    year_to: int | None


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    city: str
    street: str
    street_number: str | None
    complement: str | None
    complement_normalized: str | None
    summary: PropertySummaryOut
    timeline: list[TimelinePointOut]
    transactions: list[TransactionOut]
