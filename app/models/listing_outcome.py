from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListingOutcome(Base):
    """O que um anúncio virou depois de sair do ar.

    Uma linha por saída de anúncio, aberta no momento da saída e fechada quando
    uma quitação de ITBI no mesmo endereço aparece. Enquanto `matched_at` é
    nulo o desfecho segue em aberto e a varredura volta a procurá-lo — o ITBI
    de Belo Horizonte chega com dois meses de atraso, então nenhum desfecho
    fecha no mesmo dia em que abre.

    É a única medida do projeto que responde se um alerta prestou, em vez de se
    uma estimativa acertou outro número estimado.
    """

    __tablename__ = "listing_outcomes"
    __table_args__ = (
        UniqueConstraint("source", "listing_id", "delisted_at", name="uq_listing_outcomes_saida"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    listing_id: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    delisted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    preco_anunciado: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    preco_estimado: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    desconto_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    nota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo_referencia: Mapped[str | None] = mapped_column(String(30), nullable=True)

    transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    settlement_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    valor_realizado: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Quantas quitações disputaram o par. Mais de uma é ambiguidade honesta, e
    # quem for ler o desfecho precisa saber disso.
    candidatos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
