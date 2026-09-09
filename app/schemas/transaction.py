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
    # Saída, não dado gravado: o nominal continua sendo a única verdade e a
    # única entrada da referência de preço. Nulo quando o mês da quitação não
    # tem índice publicado.
    declared_value_corrected: float | None = None
    price_per_m2_corrected: float | None = None


class TransactionList(BaseModel):
    total: int
    items: list[TransactionOut]
    # Mesma para a página inteira; repetir por item só engordaria a resposta.
    correction_reference: date | None = None


class UploadResult(BaseModel):
    city: str
    inserted: int
    total_rows: int
