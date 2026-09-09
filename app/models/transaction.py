from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base
from app.domain.slugs import street_search_text


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city: Mapped[str] = mapped_column(String(100), index=True)
    source_row_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    raw_address: Mapped[str] = mapped_column(String(500))
    street: Mapped[str] = mapped_column(String(300))
    # Forma comparável da rua: a busca por texto casa contra ela para que
    # acento digitado (ou ausente) não decida se a quitação aparece.
    street_search: Mapped[str | None] = mapped_column(
        String(300), nullable=True, index=True
    )
    street_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complement: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(9), nullable=True)
    neighborhood: Mapped[str] = mapped_column(String(150), index=True)
    construction_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    land_area: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    built_area_acquired: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    acquired_area_total: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    finish_standard: Mapped[str | None] = mapped_column(String(10), nullable=True)
    acquired_fraction: Mapped[float | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    construction_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    occupation_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    declared_value: Mapped[float] = mapped_column(Numeric(14, 2))
    calc_base_value: Mapped[float] = mapped_column(Numeric(14, 2))
    zoning: Mapped[str | None] = mapped_column(String(20), nullable=True)
    settlement_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @validates("street")
    def _sync_street_search(self, _key: str, value: str) -> str:
        # Só cobre a escrita pelo ORM. A ingestão insere pelo Core e traz a
        # coluna pronta de `ParsedTransaction`.
        self.street_search = street_search_text(value)
        return value
