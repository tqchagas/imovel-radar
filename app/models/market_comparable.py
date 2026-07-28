from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketComparable(Base):
    __tablename__ = "market_comparables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    listing_id: Mapped[str] = mapped_column(String(100), index=True)
    cidade: Mapped[str | None] = mapped_column(String(150), nullable=True)
    tipo_imovel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parking_spaces: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suites: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_util_m2: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    preco_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    condominium_value: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    iptu_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    price_suggestion_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_suggestion_lower_bound: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    price_suggestion_price: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    price_suggestion_upper_bound: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    price_suggestion_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
