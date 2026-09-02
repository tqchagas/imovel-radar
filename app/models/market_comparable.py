from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketComparable(Base):
    __tablename__ = "market_comparables"
    __table_args__ = (
        UniqueConstraint("source", "listing_id", name="uq_market_comparables_source_listing"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    listing_id: Mapped[str] = mapped_column(String(100), index=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    cidade: Mapped[str | None] = mapped_column(String(150), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(150), nullable=True)
    rua: Mapped[str | None] = mapped_column(String(300), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cidade_normalizada: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    bairro_normalizado: Mapped[str | None] = mapped_column(String(150), nullable=True, index=True)
    rua_normalizada: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    numero_normalizado: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tipo_imovel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    coordinate_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    area_origem: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Quando o portal publicou o anuncio, quando ele informa (Loft e VivaReal).
    anunciado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parking_spaces: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suites: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_util_m2: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    preco_total: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # Ambos mensais e declarados pelo anunciante. O VivaReal publica o IPTU
    # anual e o coletor divide por doze; o Loft ja publica mensal (mediana de
    # R$ 180, ~0,18% do valor ao ano, coerente com a aliquota de BH).
    condominium_value: Mapped[float | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    iptu_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    ativo: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    collection_scope_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    activation_event_id: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    preco_estimado: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    desconto_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    desconto_reais: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    tipo_referencia: Mapped[str | None] = mapped_column(String(30), nullable=True)
    amostra_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referencia_data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    referencia_data_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    confianca: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nota: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    nota_itbi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nota_qpreco: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qpreco_desconto_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    dispersao_relativa: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    fator_calibracao: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    unidade_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    oportunidade_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    oportunidade_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
