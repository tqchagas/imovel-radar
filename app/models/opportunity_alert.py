from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base


class OpportunityAlertConfig(Base):
    __tablename__ = "opportunity_alert_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    singleton_key: Mapped[str] = mapped_column(
        String(20), nullable=False, default="global"
    )
    cidade: Mapped[str] = mapped_column(String(150), nullable=False)
    bairros_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    desconto_minimo_pct: Mapped[float] = mapped_column(
        Numeric(7, 4), nullable=False, default=0.15
    )
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
        CheckConstraint(
            "periodicidade_minutos > 0",
            name="ck_opportunity_alert_configs_periodicity",
        ),
        CheckConstraint(
            "desconto_minimo_pct >= 0",
            name="ck_opportunity_alert_configs_discount",
        ),
        CheckConstraint(
            "rule_version > 0",
            name="ck_opportunity_alert_configs_rule_version",
        ),
        CheckConstraint(
            "singleton_key = 'global'",
            name="ck_opportunity_alert_configs_singleton",
        ),
        UniqueConstraint("singleton_key", name="uq_opportunity_alert_configs_singleton"),
    )

    @validates("periodicidade_minutos")
    def validate_periodicidade_minutos(self, key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("periodicidade_minutos must be positive")
        return value

    @validates("desconto_minimo_pct")
    def validate_desconto_minimo_pct(self, key: str, value: float) -> float:
        if value < 0:
            raise ValueError("desconto_minimo_pct must be non-negative")
        return value

    @validates("rule_version")
    def validate_rule_version(self, key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("rule_version must be positive")
        return value

    @validates("timezone")
    def validate_timezone(self, key: str, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


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
    # Snapshot of the numbers this alert carried: the baseline for the next run.
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
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
            "fingerprint",
            name="uq_opportunity_notifications_dedup",
        ),
    )
