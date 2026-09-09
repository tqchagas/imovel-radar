"""A série de um índice de preços, mês a mês, como a fonte publica.

Guarda a variação percentual do mês, não o número-índice acumulado: o
acumulado depende do mês de referência escolhido, então gravá-lo congelaria
uma decisão de leitura dentro do dado. Assim a série fica auditável linha a
linha contra a fonte.
"""

from datetime import date

from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SERIE_IPCA = "ipca"


class MonetaryIndex(Base):
    __tablename__ = "monetary_index"
    __table_args__ = (
        UniqueConstraint("series", "competencia", name="uq_monetary_index_serie_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # A coluna existe para o dia em que entrar IGP-M sem migração de dado.
    series: Mapped[str] = mapped_column(String(20), index=True)
    # Sempre dia 1: a competência é o mês, e o dia só criaria chave duplicada.
    competencia: Mapped[date] = mapped_column(Date)
    variacao_pct: Mapped[float] = mapped_column(Numeric(8, 4))
