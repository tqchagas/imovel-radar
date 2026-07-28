from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city: str
    raw_address: str
    street: str
    street_number: str | None
    complement: str | None
    postal_code: str | None
    neighborhood: str
    construction_year: int | None
    land_area: float | None
    built_area_acquired: float | None
    acquired_area_total: float | None
    finish_standard: str | None
    acquired_fraction: float | None
    construction_type: str | None
    occupation_type: str | None
    declared_value: float
    calc_base_value: float
    zoning: str | None
    settlement_date: date
    created_at: datetime


class TransactionList(BaseModel):
    total: int
    items: list[TransactionOut]


class UploadResult(BaseModel):
    city: str
    inserted: int
    total_rows: int
