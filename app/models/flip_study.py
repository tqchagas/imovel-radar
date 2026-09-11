"""Um estudo de flip salvo: as entradas e a cópia das premissas usadas.

Nada de lucro, ROI ou MAO em coluna: eles são função das entradas mais o
snapshot, e coluna derivada envelhece torta na primeira mudança de fórmula.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUS_VALIDOS = ("oportunidade", "em_analise", "descartado")
ORIGENS_VALIDAS = ("manual", "oportunidade", "leilao")


class FlipStudy(Base):
    __tablename__ = "flip_studies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    apelido: Mapped[str | None] = mapped_column(String(150), nullable=True)
    endereco: Mapped[str] = mapped_column(String(300), nullable=False)
    bairro: Mapped[str | None] = mapped_column(String(150), nullable=True)
    cidade: Mapped[str] = mapped_column(String(150), nullable=False, default="belo_horizonte")

    area_util_m2: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    area_seca_m2: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quartos: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    banheiros: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cozinhas: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    portas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    preco_compra: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    arv_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    meses_carrego: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    eletrica_completa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hidraulica_completa_banheiro: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    hidraulica_completa_cozinha: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="em_analise")
    # Sem chave estrangeira: o anúncio de origem pode sair do radar, e o estudo
    # não deve sair junto com ele.
    origem: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    origem_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    premissas_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('oportunidade', 'em_analise', 'descartado')",
            name="ck_flip_studies_status",
        ),
        CheckConstraint(
            "origem IN ('manual', 'oportunidade', 'leilao')",
            name="ck_flip_studies_origem",
        ),
        CheckConstraint("area_seca_m2 > 0", name="ck_flip_studies_area_seca"),
        CheckConstraint("preco_compra > 0", name="ck_flip_studies_preco"),
        CheckConstraint("meses_carrego >= 0", name="ck_flip_studies_meses"),
    )
