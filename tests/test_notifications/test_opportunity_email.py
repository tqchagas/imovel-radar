import json
from datetime import date, datetime, timedelta

import pytest

from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import OpportunityAlertConfig, OpportunityNotification
from app.notifications.email import EmailMessage, render_opportunity_email
from app.services.opportunity_notifications import (
    DEDUP_WINDOW_HOURS,
    PENDING_RETRY_AFTER_HOURS,
    RESEND_DISCOUNT_POINTS,
    RESEND_ESTIMATE_PCT,
    RESEND_PRICE_PCT,
    send_opportunity_alerts,
)

NOW = datetime(2026, 8, 20, 9, 0)
RECIPIENTS = ["alerta@example.com", "socio@example.com"]


class Recorder:
    def __init__(self, fail: bool = False) -> None:
        self.messages: list[EmailMessage] = []
        self.fail = fail

    def __call__(self, message: EmailMessage) -> None:
        if self.fail:
            raise RuntimeError("smtp down")
        self.messages.append(message)


def config(db, **kwargs) -> OpportunityAlertConfig:
    row = OpportunityAlertConfig(
        cidade="belo_horizonte",
        bairros_json=kwargs.pop("bairros_json", "[]"),
        desconto_minimo_pct=kwargs.pop("desconto_minimo_pct", 0.15),
        confianca_minima=kwargs.pop("confianca_minima", "media"),
        destinatarios_json=kwargs.pop("destinatarios_json", json.dumps(RECIPIENTS)),
        periodicidade_minutos=kwargs.pop("periodicidade_minutos", 720),
        rule_version=kwargs.pop("rule_version", 1),
        enabled=kwargs.pop("enabled", True),
    )
    db.add(row)
    return row


def listing(
    db,
    *,
    listing_id: str = "qa-1",
    bairro: str = "Savassi",
    preco_total: float = 500000.0,
    preco_estimado: float = 800000.0,
    desconto_pct: float = 0.375,
    confianca: str = "alta",
    ativo: bool = True,
    activation_event_id: int = 1,
    fingerprint: str | None = "f" * 64,
) -> MarketComparable:
    row = MarketComparable(
        source="quintoandar",
        listing_id=listing_id,
        url=f"https://example.com/{listing_id}",
        cidade="Belo Horizonte",
        bairro=bairro,
        rua="Rua Sao Joao",
        numero="10",
        cidade_normalizada="belo_horizonte",
        bairro_normalizado=bairro.lower().replace(" ", "_"),
        rua_normalizada="rua_sao_joao",
        numero_normalizado="10",
        tipo_imovel="APARTAMENTO",
        bedrooms=3,
        area_util_m2=80.0,
        preco_total=preco_total,
        ativo=ativo,
        activation_event_id=activation_event_id,
        preco_estimado=preco_estimado,
        desconto_pct=desconto_pct,
        desconto_reais=preco_estimado - preco_total,
        tipo_referencia="endereco_exato",
        amostra_count=42,
        referencia_data_inicio=date(2024, 6, 30),
        referencia_data_fim=date(2026, 6, 30),
        confianca=confianca,
        oportunidade_motivo="Mediana de 42 ITBIs residenciais por endereço exato.",
        oportunidade_fingerprint=fingerprint,
        first_seen_at=datetime(2026, 8, 1),
        last_seen_at=datetime(2026, 8, 20, 8, 55),
    )
    db.add(row)
    return row


def notifications(db) -> list[OpportunityNotification]:
    return db.query(OpportunityNotification).order_by(OpportunityNotification.id).all()


def test_first_eligibility_sends_one_event_with_every_recipient(db_session) -> None:
    config(db_session)
    row = listing(db_session)
    db_session.flush()
    sender = Recorder()

    summary = send_opportunity_alerts(db_session, sender=sender, now=NOW)

    assert summary["sent"] == 1
    assert len(sender.messages) == 1
    assert list(sender.messages[0].recipients) == RECIPIENTS
    events = notifications(db_session)
    assert len(events) == 1
    assert events[0].status == "sent"
    assert events[0].sent_at == NOW
    assert events[0].market_comparable_id == row.id
    assert json.loads(events[0].destinatarios_json) == RECIPIENTS


def test_low_confidence_and_small_discount_are_not_sent(db_session) -> None:
    config(db_session)
    listing(db_session, listing_id="baixa", confianca="baixa")
    listing(db_session, listing_id="pouco-desconto", desconto_pct=0.1)
    listing(db_session, listing_id="sem-fingerprint", fingerprint=None)
    listing(db_session, listing_id="inativo", ativo=False)
    db_session.flush()
    sender = Recorder()

    summary = send_opportunity_alerts(db_session, sender=sender, now=NOW)

    assert summary["sent"] == 0
    assert sender.messages == []
    assert notifications(db_session) == []


def test_confidence_minimum_is_honoured(db_session) -> None:
    config(db_session, confianca_minima="alta")
    listing(db_session, listing_id="media", confianca="media")
    db_session.flush()

    summary = send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)

    assert summary["sent"] == 0


def test_neighborhood_scope_filters_listings(db_session) -> None:
    config(db_session, bairros_json=json.dumps(["Savassi"]))
    listing(db_session, listing_id="dentro", bairro="Savassi")
    listing(db_session, listing_id="fora", bairro="Lourdes")
    db_session.flush()
    sender = Recorder()

    send_opportunity_alerts(db_session, sender=sender, now=NOW)

    assert len(sender.messages) == 1
    assert "Savassi" in sender.messages[0].body


def test_disabled_or_missing_config_never_sends(db_session) -> None:
    listing(db_session)
    db_session.flush()
    assert send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)["status"] == "disabled"

    config(db_session, enabled=False)
    db_session.flush()
    assert send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)["status"] == "disabled"


def test_no_resend_within_the_24h_window(db_session) -> None:
    config(db_session)
    listing(db_session)
    db_session.flush()
    send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)

    later = NOW + timedelta(hours=DEDUP_WINDOW_HOURS) - timedelta(minutes=1)
    row = db_session.query(MarketComparable).one()
    row.preco_total = 300000.0
    row.desconto_pct = 0.625
    row.oportunidade_fingerprint = "a" * 64
    db_session.flush()

    summary = send_opportunity_alerts(db_session, sender=Recorder(), now=later)

    assert summary["sent"] == 0
    assert len(notifications(db_session)) == 1


def test_unchanged_opportunity_is_not_resent_after_the_window(db_session) -> None:
    config(db_session)
    listing(db_session)
    db_session.flush()
    send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)

    later = NOW + timedelta(days=5)
    summary = send_opportunity_alerts(db_session, sender=Recorder(), now=later)

    assert summary["sent"] == 0
    assert len(notifications(db_session)) == 1


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("preco_total", 500000.0 * (1 - RESEND_PRICE_PCT), True),
        ("preco_total", 500000.0 * (1 - RESEND_PRICE_PCT / 2), False),
        ("preco_estimado", 800000.0 * (1 + RESEND_ESTIMATE_PCT), True),
        ("preco_estimado", 800000.0 * (1 + RESEND_ESTIMATE_PCT / 2), False),
        ("desconto_pct", 0.375 + RESEND_DISCOUNT_POINTS, True),
        ("desconto_pct", 0.375 + RESEND_DISCOUNT_POINTS / 2, False),
    ],
)
def test_resend_thresholds(db_session, field, value, expected) -> None:
    config(db_session)
    listing(db_session)
    db_session.flush()
    send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)

    row = db_session.query(MarketComparable).one()
    setattr(row, field, value)
    row.oportunidade_fingerprint = "b" * 64
    db_session.flush()

    later = NOW + timedelta(days=2)
    summary = send_opportunity_alerts(db_session, sender=Recorder(), now=later)

    assert summary["sent"] == int(expected)


def test_reactivation_sends_again_even_with_the_same_fingerprint(db_session) -> None:
    config(db_session)
    listing(db_session)
    db_session.flush()
    send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)

    row = db_session.query(MarketComparable).one()
    row.activation_event_id = 2
    db_session.flush()

    later = NOW + timedelta(days=2)
    summary = send_opportunity_alerts(db_session, sender=Recorder(), now=later)

    assert summary["sent"] == 1
    events = notifications(db_session)
    assert [event.activation_event_id for event in events] == [1, 2]


def test_failed_send_is_recorded_and_retried_later(db_session) -> None:
    config(db_session)
    listing(db_session)
    db_session.flush()

    summary = send_opportunity_alerts(db_session, sender=Recorder(fail=True), now=NOW)

    assert summary["failed"] == 1
    events = notifications(db_session)
    assert events[0].status == "failed"
    assert events[0].sent_at is None
    assert "smtp down" in events[0].error

    later = NOW + timedelta(minutes=30)
    sender = Recorder()
    summary = send_opportunity_alerts(db_session, sender=sender, now=later)

    assert summary["sent"] == 1
    assert len(sender.messages) == 1
    events = notifications(db_session)
    assert len(events) == 1
    assert events[0].status == "sent"
    assert events[0].sent_at == later


def test_abandoned_pending_is_retried_only_after_an_hour(db_session) -> None:
    config(db_session)
    row = listing(db_session)
    db_session.flush()
    db_session.add(
        OpportunityNotification(
            market_comparable_id=row.id,
            rule_version=1,
            activation_event_id=1,
            status="pending",
            fingerprint="f" * 64,
            destinatarios_json=json.dumps(RECIPIENTS),
            created_at=NOW,
        )
    )
    db_session.flush()

    early = NOW + timedelta(hours=PENDING_RETRY_AFTER_HOURS) - timedelta(minutes=1)
    assert send_opportunity_alerts(db_session, sender=Recorder(), now=early)["sent"] == 0

    late = NOW + timedelta(hours=PENDING_RETRY_AFTER_HOURS, minutes=1)
    summary = send_opportunity_alerts(db_session, sender=Recorder(), now=late)

    assert summary["sent"] == 1
    events = notifications(db_session)
    assert len(events) == 1
    assert events[0].status == "sent"


def test_dry_run_reports_without_sending_or_persisting(db_session) -> None:
    config(db_session)
    listing(db_session)
    db_session.flush()
    sender = Recorder()

    summary = send_opportunity_alerts(db_session, sender=sender, now=NOW, dry_run=True)

    assert summary["eligible"] == 1
    assert summary["sent"] == 0
    assert sender.messages == []
    assert notifications(db_session) == []


def test_rule_version_change_alone_does_not_resend(db_session) -> None:
    alert_config = config(db_session)
    listing(db_session)
    db_session.flush()
    send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)

    alert_config.rule_version = 2
    db_session.flush()

    later = NOW + timedelta(days=3)
    summary = send_opportunity_alerts(db_session, sender=Recorder(), now=later)

    assert summary["sent"] == 0


def test_operator_can_force_an_initial_dispatch(db_session) -> None:
    alert_config = config(db_session)
    listing(db_session)
    db_session.flush()
    send_opportunity_alerts(db_session, sender=Recorder(), now=NOW)

    alert_config.rule_version = 2
    db_session.flush()

    later = NOW + timedelta(days=3)
    summary = send_opportunity_alerts(
        db_session, sender=Recorder(), now=later, force_initial=True
    )

    assert summary["sent"] == 1
    assert [event.rule_version for event in notifications(db_session)] == [1, 2]


def test_email_body_carries_the_calculation_context(db_session) -> None:
    config(db_session)
    listing(db_session)
    db_session.flush()
    sender = Recorder()

    send_opportunity_alerts(db_session, sender=sender, now=NOW)

    message = sender.messages[0]
    assert "37,5%" in message.subject
    for expected in (
        "Rua Sao Joao, 10",
        "QuintoAndar",
        "R$ 500.000",
        "R$ 800.000",
        "Alta",
        "42",
        "30/06/2024",
        "30/06/2026",
        "https://example.com/qa-1",
    ):
        assert expected in message.body, expected


def test_render_is_deterministic(db_session) -> None:
    config(db_session)
    row = listing(db_session)
    db_session.flush()

    assert render_opportunity_email(row, RECIPIENTS) == render_opportunity_email(row, RECIPIENTS)
