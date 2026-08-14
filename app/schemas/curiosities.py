from datetime import date

from pydantic import BaseModel


class UnitRefOut(BaseModel):
    street: str
    street_number: str | None
    complement: str | None
    neighborhood: str


class BuildingStatOut(BaseModel):
    street: str
    street_number: str | None
    neighborhood: str
    transaction_count: int
    unit_count: int
    median_price_per_m2: float | None
    last_settlement_date: date


class UnitStatOut(BaseModel):
    unit: UnitRefOut
    transaction_count: int
    first_settlement_date: date
    last_settlement_date: date
    last_value: float


class AppreciationStatOut(BaseModel):
    unit: UnitRefOut
    from_date: date
    from_value: float
    to_date: date
    to_value: float
    total_pct: float
    years: float
    annualized_pct: float


class FlipStatOut(BaseModel):
    unit: UnitRefOut
    from_date: date
    from_value: float
    to_date: date
    to_value: float
    days: int
    delta_pct: float


class RecordSaleOut(BaseModel):
    unit: UnitRefOut
    settlement_date: date
    declared_value: float
    built_area_acquired: float | None
    price_per_m2: float | None
    construction_type: str | None


class MonthCountOut(BaseModel):
    year: int
    month: int
    transaction_count: int


class NeighborhoodSpreadOut(BaseModel):
    neighborhood: str
    transaction_count: int
    p25_ticket: float
    median_ticket: float
    p75_ticket: float
    spread_ratio: float


class InsightItemOut(BaseModel):
    slug: str
    title: str
    description: str
    count: int
    url: str


class CuriosityInsightsOut(BaseModel):
    city: str
    transaction_count: int
    items: list[InsightItemOut]


class MoverOut(BaseModel):
    neighborhood: str
    transaction_count: int
    median_price_per_m2: float | None
    delta_pct: float


class CuriositiesOut(BaseModel):
    city: str | None
    reference_date: date | None
    months: int
    transaction_count: int
    top_buildings: list[BuildingStatOut]
    top_buildings_recent: list[BuildingStatOut]
    top_units: list[UnitStatOut]
    top_appreciation: list[AppreciationStatOut]
    fastest_flips: list[FlipStatOut]
    priciest_sales: list[RecordSaleOut]
    priciest_per_m2: list[RecordSaleOut]
    by_month: list[MonthCountOut]
    risers: list[MoverOut]
    fallers: list[MoverOut]
    widest_spread: list[NeighborhoodSpreadOut]
