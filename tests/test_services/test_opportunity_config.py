import json

import pytest

from app.models.opportunity_alert import OpportunityAlertConfig
from app.services.opportunity_notifications import load_config, upsert_alert_config


def test_bootstrap_creates_the_global_configuration(db_session) -> None:
    config = upsert_alert_config(
        db_session,
        cidade="belo_horizonte",
        bairros=["Savassi", "Lourdes"],
        destinatarios=["alerta@example.com"],
    )

    assert config.singleton_key == "global"
    assert json.loads(config.bairros_json) == ["Savassi", "Lourdes"]
    assert config.rule_version == 1
    assert load_config(db_session) is not None


def test_rule_changes_bump_the_rule_version(db_session) -> None:
    upsert_alert_config(db_session, cidade="belo_horizonte", destinatarios=["a@x.com"])

    updated = upsert_alert_config(
        db_session, cidade="belo_horizonte", destinatarios=["a@x.com"], desconto_minimo_pct=0.2
    )

    assert updated.rule_version == 2
    assert db_session.query(OpportunityAlertConfig).count() == 1


def test_recipient_only_changes_keep_the_rule_version(db_session) -> None:
    upsert_alert_config(db_session, cidade="belo_horizonte", destinatarios=["a@x.com"])

    updated = upsert_alert_config(
        db_session, cidade="belo_horizonte", destinatarios=["a@x.com", "b@x.com"]
    )

    assert updated.rule_version == 1
    assert json.loads(updated.destinatarios_json) == ["a@x.com", "b@x.com"]


def test_disabled_configuration_stops_the_job(db_session) -> None:
    upsert_alert_config(
        db_session, cidade="belo_horizonte", destinatarios=["a@x.com"], enabled=False
    )

    assert load_config(db_session) is None


def test_invalid_values_are_rejected(db_session) -> None:
    with pytest.raises(ValueError):
        upsert_alert_config(
            db_session, cidade="belo_horizonte", destinatarios=["a@x.com"], confianca_minima="otima"
        )
    with pytest.raises(ValueError):
        upsert_alert_config(
            db_session, cidade="belo_horizonte", destinatarios=["a@x.com"], periodicidade_minutos=0
        )
    with pytest.raises(ValueError):
        upsert_alert_config(db_session, cidade="belo_horizonte", destinatarios=[])
