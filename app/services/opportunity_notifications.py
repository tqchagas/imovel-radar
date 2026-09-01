"""Transactional, deduplicated dispatch of opportunity alerts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from app.domain.opportunities import CONFIDENCE_ORDER
from app.domain.slugs import address_key
from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import OpportunityAlertConfig, OpportunityNotification
from app.notifications.email import EmailMessage, render_opportunity_email, send_email

RESEND_PRICE_PCT = 0.03
RESEND_DISCOUNT_POINTS = 0.05
RESEND_ESTIMATE_PCT = 0.05
DEDUP_WINDOW_HOURS = 24
PENDING_RETRY_AFTER_HOURS = 1

Sender = Callable[[EmailMessage], None]


def _as_float(value) -> float | None:
    return float(value) if value is not None else None


def _as_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def load_config(db: Session) -> OpportunityAlertConfig | None:
    """The single global configuration, when the job is enabled."""
    config = db.scalar(
        select(OpportunityAlertConfig).where(OpportunityAlertConfig.singleton_key == "global")
    )
    return config if config is not None and config.enabled else None


def upsert_alert_config(
    db: Session,
    *,
    cidade: str,
    destinatarios: list[str],
    bairros: list[str] | None = None,
    desconto_minimo_pct: float = 0.15,
    confianca_minima: str = "media",
    periodicidade_minutos: int = 720,
    timezone_name: str = "America/Sao_Paulo",
    enabled: bool = True,
    commit: bool = True,
) -> OpportunityAlertConfig:
    """Explicit bootstrap/update of the single global alert configuration."""
    if confianca_minima not in CONFIDENCE_ORDER:
        raise ValueError(f"invalid confianca_minima:{confianca_minima}")
    if periodicidade_minutos <= 0:
        raise ValueError("periodicidade_minutos must be positive")
    if desconto_minimo_pct < 0:
        raise ValueError("desconto_minimo_pct must be non-negative")
    if not destinatarios:
        raise ValueError("at least one recipient is required")

    bairros_json = json.dumps(list(bairros or []), ensure_ascii=False)
    config = db.scalar(
        select(OpportunityAlertConfig).where(OpportunityAlertConfig.singleton_key == "global")
    )
    if config is None:
        config = OpportunityAlertConfig(
            singleton_key="global",
            cidade=cidade,
            bairros_json=bairros_json,
            desconto_minimo_pct=desconto_minimo_pct,
            confianca_minima=confianca_minima,
            destinatarios_json=json.dumps(destinatarios, ensure_ascii=False),
            periodicidade_minutos=periodicidade_minutos,
            timezone=timezone_name,
            rule_version=1,
            enabled=enabled,
        )
        db.add(config)
    else:
        # Only rule-affecting parameters start a new baseline; recipients do not.
        rule_changed = (
            config.cidade != cidade
            or config.bairros_json != bairros_json
            or float(config.desconto_minimo_pct) != float(desconto_minimo_pct)
            or config.confianca_minima != confianca_minima
        )
        config.cidade = cidade
        config.bairros_json = bairros_json
        config.desconto_minimo_pct = desconto_minimo_pct
        config.confianca_minima = confianca_minima
        config.destinatarios_json = json.dumps(destinatarios, ensure_ascii=False)
        config.periodicidade_minutos = periodicidade_minutos
        config.timezone = timezone_name
        config.enabled = enabled
        if rule_changed:
            config.rule_version += 1
    if commit:
        db.commit()
    else:
        db.flush()
    return config


def _acquire_config_lock(db: Session, config: OpportunityAlertConfig) -> None:
    """Serialize concurrent jobs so two runs cannot alert the same listing."""
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        db.execute(
            select(OpportunityAlertConfig.id)
            .where(OpportunityAlertConfig.id == config.id)
            .with_for_update()
        )
    elif dialect == "sqlite":
        if not db.in_transaction():
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    else:
        raise RuntimeError(f"unsupported_database_dialect:{dialect}")


def eligible_listings(
    db: Session, config: OpportunityAlertConfig
) -> list[MarketComparable]:
    """Active listings inside the configured scope that clear discount and confidence."""
    allowed = [
        level
        for level, rank in CONFIDENCE_ORDER.items()
        if rank >= CONFIDENCE_ORDER[config.confianca_minima]
    ]
    stmt = (
        select(MarketComparable)
        .where(
            MarketComparable.ativo.is_(True),
            MarketComparable.cidade_normalizada == address_key(config.cidade),
            MarketComparable.oportunidade_fingerprint.is_not(None),
            MarketComparable.confianca.in_(allowed),
            MarketComparable.desconto_pct >= config.desconto_minimo_pct,
        )
        .order_by(MarketComparable.id)
    )
    bairros = [address_key(name) for name in json.loads(config.bairros_json or "[]")]
    bairros = [name for name in bairros if name]
    if bairros:
        stmt = stmt.where(MarketComparable.bairro_normalizado.in_(bairros))
    return list(db.scalars(stmt))


def snapshot(listing: MarketComparable) -> dict:
    """Numbers a later run compares against to decide on a resend."""
    return {
        "preco_anunciado": _as_float(listing.preco_total),
        "preco_estimado": _as_float(listing.preco_estimado),
        "desconto_pct": _as_float(listing.desconto_pct),
    }


def _changed_enough(current: dict, previous: dict | None) -> bool:
    if not previous:
        return True
    for key, threshold in (
        ("preco_anunciado", RESEND_PRICE_PCT),
        ("preco_estimado", RESEND_ESTIMATE_PCT),
    ):
        new, old = current.get(key), previous.get(key)
        if new is None or not old:
            return True
        # Round to the stored precision: float noise must not trip a threshold.
        if round(abs(new - old) / abs(old), 6) >= threshold:
            return True
    new, old = current.get("desconto_pct"), previous.get("desconto_pct")
    if new is None or old is None:
        return True
    return round(abs(new - old), 4) >= RESEND_DISCOUNT_POINTS


def _last_sent(db: Session, listing: MarketComparable) -> OpportunityNotification | None:
    return db.scalar(
        select(OpportunityNotification)
        .where(
            OpportunityNotification.market_comparable_id == listing.id,
            OpportunityNotification.status == "sent",
        )
        .order_by(desc(OpportunityNotification.sent_at), desc(OpportunityNotification.id))
        .limit(1)
    )


def _retryable(
    db: Session, listing: MarketComparable, config: OpportunityAlertConfig, now: datetime
) -> OpportunityNotification | None:
    """A failed event, or a pending one abandoned for over an hour."""
    row = db.scalar(
        select(OpportunityNotification).where(
            OpportunityNotification.market_comparable_id == listing.id,
            OpportunityNotification.rule_version == config.rule_version,
            OpportunityNotification.activation_event_id == listing.activation_event_id,
            OpportunityNotification.fingerprint == listing.oportunidade_fingerprint,
        )
    )
    if row is None or row.status == "sent":
        return None
    if row.status == "failed":
        return row
    abandoned_at = row.created_at + timedelta(hours=PENDING_RETRY_AFTER_HOURS)
    return row if now > abandoned_at else None


def _already_dispatched(
    db: Session, listing: MarketComparable, config: OpportunityAlertConfig
) -> bool:
    return (
        db.scalar(
            select(OpportunityNotification.id).where(
                OpportunityNotification.market_comparable_id == listing.id,
                OpportunityNotification.rule_version == config.rule_version,
                OpportunityNotification.activation_event_id == listing.activation_event_id,
                OpportunityNotification.fingerprint == listing.oportunidade_fingerprint,
                OpportunityNotification.status == "sent",
            )
        )
        is not None
    )


def _decide(
    db: Session,
    listing: MarketComparable,
    config: OpportunityAlertConfig,
    now: datetime,
    force_initial: bool,
) -> tuple[bool, OpportunityNotification | None]:
    """Whether to alert this listing now, and which event row to reuse."""
    pending = db.scalar(
        select(OpportunityNotification).where(
            OpportunityNotification.market_comparable_id == listing.id,
            OpportunityNotification.rule_version == config.rule_version,
            OpportunityNotification.activation_event_id == listing.activation_event_id,
            OpportunityNotification.fingerprint == listing.oportunidade_fingerprint,
            OpportunityNotification.status == "pending",
        )
    )
    if pending is not None and _retryable(db, listing, config, now) is None:
        return False, None

    last = _last_sent(db, listing)
    if last is not None and last.sent_at is not None:
        # One alert per listing per day, whatever changed in between.
        if now - last.sent_at < timedelta(hours=DEDUP_WINDOW_HOURS):
            return False, None
    if _already_dispatched(db, listing, config):
        return False, None

    reuse = _retryable(db, listing, config, now)
    if last is None or force_initial:
        return True, reuse
    if last.activation_event_id != listing.activation_event_id:
        # The listing came back: a new alert is warranted even if nothing changed.
        return True, reuse
    previous = json.loads(last.payload_json) if last.payload_json else None
    return _changed_enough(snapshot(listing), previous), reuse


def _event(
    listing: MarketComparable,
    config: OpportunityAlertConfig,
    recipients: list[str],
    now: datetime,
) -> OpportunityNotification:
    return OpportunityNotification(
        market_comparable_id=listing.id,
        rule_version=config.rule_version,
        activation_event_id=listing.activation_event_id,
        status="pending",
        fingerprint=listing.oportunidade_fingerprint,
        destinatarios_json=json.dumps(recipients, ensure_ascii=False),
        payload_json=json.dumps(snapshot(listing), sort_keys=True),
        created_at=now,
    )


def send_opportunity_alerts(
    db: Session,
    *,
    sender: Sender | None = None,
    now: datetime | None = None,
    force_initial: bool = False,
    dry_run: bool = False,
    commit: bool = True,
) -> dict:
    """Alert every eligible listing once, recording pending/sent/failed per event."""
    timestamp = _as_naive(now or datetime.now(timezone.utc))
    summary = {
        "status": "ok",
        "eligible": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
    }

    config = load_config(db)
    if config is None:
        summary["status"] = "disabled"
        return summary

    recipients = [str(item) for item in json.loads(config.destinatarios_json or "[]")]
    if not recipients:
        summary["status"] = "no_recipients"
        return summary

    _acquire_config_lock(db, config)
    deliver = sender or send_email

    for listing in eligible_listings(db, config):
        summary["eligible"] += 1
        should_send, reuse = _decide(db, listing, config, timestamp, force_initial)
        if not should_send:
            summary["skipped"] += 1
            continue
        if dry_run:
            continue

        event = reuse or _event(listing, config, recipients, timestamp)
        event.status = "pending"
        event.error = None
        event.destinatarios_json = json.dumps(recipients, ensure_ascii=False)
        event.payload_json = json.dumps(snapshot(listing), sort_keys=True)
        if reuse is None:
            db.add(event)
        db.flush()

        try:
            deliver(render_opportunity_email(listing, recipients))
        except Exception as error:  # noqa: BLE001 - the failure belongs in the event row
            event.status = "failed"
            event.error = str(error)
            summary["failed"] += 1
        else:
            event.status = "sent"
            event.sent_at = timestamp
            summary["sent"] += 1
        db.flush()

    if commit:
        db.commit()
    return summary
