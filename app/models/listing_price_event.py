from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListingPriceEvent(Base):
    """One row per observed change in a listing's life.

    Without this there is no way to tell whether an alert was any good: a
    listing that quietly drops 20% and then disappears is the signal that it
    sold, and comparing that against what the model said at the time is the
    only ground truth available. The comparables table only ever holds the
    latest state, so the history has to be written as it happens.
    """

    __tablename__ = "listing_price_events"
    __table_args__ = (
        Index("ix_listing_price_events_listing", "source", "listing_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    listing_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # "listed" first sight, "price_changed", "delisted" when it stops appearing,
    # "relisted" when it comes back.
    event: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    preco_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    preco_anterior: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # The model's reading at the moment of the event, so a later review can ask
    # what the score said about a listing that went on to sell. Both halves are
    # kept: the final score alone cannot tell a listing that never qualified
    # from one the QuintoAndar estimate vetoed, and that is exactly the
    # comparison an outcome study has to make.
    nota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nota_itbi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nota_qpreco: Mapped[int | None] = mapped_column(Integer, nullable=True)
    desconto_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
