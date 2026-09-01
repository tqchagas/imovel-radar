from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OpportunityAlertConfig(Base):
    __tablename__ = "opportunity_alert_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cidade: Mapped[str] = mapped_column(String(150), nullable=False)
    bairros_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    desconto_minimo_pct: Mapped[float] = mapped_column(nullable=False, default=0.15)
    confianca_minima: Mapped[str] = mapped_column(String(20), nullable=False, default="media")
    destinatarios_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    periodicidade_minutos: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Sao_Paulo")
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "confianca_minima IN ('baixa', 'media', 'alta')",
            name="ck_opportunity_alert_configs_confidence",
        ),
    )


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    uf: Mapped[str] = mapped_column(String(2), nullable=False)
    cidade: Mapped[str] = mapped_column(String(150), nullable=False)
    bairros_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    filtros_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    scope_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    pages_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_collection_runs_status",
        ),
    )


class OpportunityNotification(Base):
    __tablename__ = "opportunity_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_comparable_id: Mapped[int] = mapped_column(
        ForeignKey("market_comparables.id"), nullable=False
    )
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    activation_event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    destinatarios_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="ck_opportunity_notifications_status",
        ),
        UniqueConstraint(
            "market_comparable_id",
            "rule_version",
            "activation_event_id",
            name="uq_opportunity_notifications_dedup",
        ),
    )
