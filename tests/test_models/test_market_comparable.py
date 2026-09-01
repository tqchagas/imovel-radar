from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Numeric, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import (
    CollectionRun,
    OpportunityAlertConfig,
    OpportunityNotification,
)


def test_market_comparable_stores_listing_snapshot_and_opportunity(db_session) -> None:
    comparable = MarketComparable(
        source="quintoandar",
        listing_id="listing-1",
        url="https://example.test/imovel/listing-1",
        cidade="Belo Horizonte",
        bairro="Centro",
        rua="Rua Teste",
        numero="10",
        cidade_normalizada="belo_horizonte",
        bairro_normalizado="centro",
        rua_normalizada="rua_teste",
        numero_normalizado="10",
        coordinate_source="geocoded",
        ativo=True,
        collection_scope_key="scope-1",
        first_seen_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
        preco_total=400000,
        area_util_m2=80,
        preco_estimado=500000,
        desconto_pct=0.2,
        desconto_reais=100000,
        tipo_referencia="bairro_area",
        amostra_count=18,
        referencia_data_inicio=datetime(2024, 8, 31).date(),
        referencia_data_fim=datetime(2026, 8, 31).date(),
        confianca="media",
        oportunidade_motivo="Amostra suficiente no bairro.",
    )

    db_session.add(comparable)
    db_session.commit()

    saved = db_session.query(MarketComparable).one()
    assert saved.url == "https://example.test/imovel/listing-1"
    assert saved.rua_normalizada == "rua_teste"
    assert saved.ativo is True
    assert saved.collection_scope_key == "scope-1"
    assert saved.first_seen_at is not None
    assert saved.last_seen_at is not None
    assert saved.preco_estimado == 500000
    assert saved.desconto_pct == Decimal("0.2000")
    assert saved.tipo_referencia == "bairro_area"
    assert saved.amostra_count == 18


def test_alert_config_collection_run_and_notification_are_persisted(db_session) -> None:
    config = OpportunityAlertConfig(
        cidade="belo_horizonte",
        bairros_json='["Centro", "Savassi"]',
        desconto_minimo_pct=0.15,
        confianca_minima="media",
        destinatarios_json='["alerts@example.test"]',
        periodicidade_minutos=60,
        timezone="America/Sao_Paulo",
        rule_version=3,
    )
    comparable = MarketComparable(
        source="vivareal", listing_id="listing-2", ativo=True
    )
    db_session.add_all([config, comparable])
    db_session.flush()

    run = CollectionRun(
        source="vivareal",
        uf="MG",
        cidade="belo_horizonte",
        bairros_json='["Centro"]',
        filtros_json='{"tipo": "apartamento"}',
        scope_key="scope-2",
        status="success",
    )
    notification = OpportunityNotification(
        market_comparable_id=comparable.id,
        rule_version=config.rule_version,
        activation_event_id=2,
        status="pending",
        fingerprint="fingerprint-1",
        destinatarios_json=config.destinatarios_json,
    )
    db_session.add_all([run, notification])
    db_session.commit()

    saved_config = db_session.query(OpportunityAlertConfig).one()
    saved_run = db_session.query(CollectionRun).one()
    saved_notification = db_session.query(OpportunityNotification).one()
    assert saved_config.bairros_json == '["Centro", "Savassi"]'
    assert saved_config.destinatarios_json == '["alerts@example.test"]'
    assert saved_config.periodicidade_minutos == 60
    assert saved_config.rule_version == 3
    assert saved_run.scope_key == "scope-2"
    assert saved_notification.status == "pending"
    assert saved_notification.fingerprint == "fingerprint-1"
    assert saved_notification.activation_event_id == 2


def test_alert_config_discount_metadata_matches_migration() -> None:
    column = OpportunityAlertConfig.__table__.c.desconto_minimo_pct

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 7
    assert column.type.scale == 4


def test_alert_config_is_singleton(db_session) -> None:
    db_session.add_all(
        [
            OpportunityAlertConfig(cidade="belo_horizonte", periodicidade_minutos=60),
            OpportunityAlertConfig(cidade="belo_horizonte", periodicidade_minutos=120),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("periodicidade_minutos", 0),
        ("desconto_minimo_pct", -0.01),
        ("rule_version", 0),
        ("timezone", "Not/A_Timezone"),
    ],
)
def test_alert_config_rejects_invalid_values(field: str, value, db_session) -> None:
    with pytest.raises(ValueError):
        values = {
            "cidade": "belo_horizonte",
            "periodicidade_minutos": 60,
            field: value,
        }
        OpportunityAlertConfig(**values)


@pytest.mark.parametrize("status", ["pending", "sent", "failed"])
def test_notification_accepts_allowed_statuses(db_session, status: str) -> None:
    comparable = MarketComparable(source="quintoandar", listing_id=status)
    db_session.add(comparable)
    db_session.flush()
    expected_fingerprint = f"fp-{status}"
    db_session.add(
        OpportunityNotification(
            market_comparable_id=comparable.id,
            rule_version=1,
            activation_event_id=1,
            status=status,
            fingerprint=expected_fingerprint,
        )
    )
    db_session.commit()
    assert (
        db_session.query(OpportunityNotification).one().fingerprint
        == expected_fingerprint
    )


def test_notification_rejects_unknown_status(db_session) -> None:
    comparable = MarketComparable(source="quintoandar", listing_id="invalid")
    db_session.add(comparable)
    db_session.flush()
    db_session.add(
        OpportunityNotification(
            market_comparable_id=comparable.id,
            rule_version=1,
            activation_event_id=1,
            status="queued",
            fingerprint="fp-invalid",
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_market_comparable_identity_is_source_and_listing_id(db_session) -> None:
    db_session.add_all(
        [
            MarketComparable(source="quintoandar", listing_id="same-id"),
            MarketComparable(source="vivareal", listing_id="same-id"),
        ]
    )
    db_session.commit()

    db_session.add(MarketComparable(source="quintoandar", listing_id="same-id"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_notification_identity_prevents_duplicate_fingerprints(db_session) -> None:
    comparable = MarketComparable(source="quintoandar", listing_id="dedup")
    db_session.add(comparable)
    db_session.flush()
    db_session.add_all(
        [
            OpportunityNotification(
                market_comparable_id=comparable.id,
                rule_version=1,
                activation_event_id=1,
                status="pending",
                fingerprint="first",
            ),
            OpportunityNotification(
                market_comparable_id=comparable.id,
                rule_version=1,
                activation_event_id=1,
                status="pending",
                fingerprint="first",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_notification_allows_new_fingerprint_for_same_activation(db_session) -> None:
    comparable = MarketComparable(source="quintoandar", listing_id="resend")
    db_session.add(comparable)
    db_session.flush()
    db_session.add_all(
        [
            OpportunityNotification(
                market_comparable_id=comparable.id,
                rule_version=1,
                activation_event_id=1,
                status="sent",
                fingerprint="first",
            ),
            OpportunityNotification(
                market_comparable_id=comparable.id,
                rule_version=1,
                activation_event_id=1,
                status="pending",
                fingerprint="second",
            ),
        ]
    )
    db_session.commit()

    assert db_session.query(OpportunityNotification).count() == 2


def test_migration_preserves_most_complete_legacy_comparable(
    tmp_path: Path, monkeypatch
) -> None:
    """Exercise SQLite migrations; PostgreSQL needs a separate integration run."""
    database_url = f"sqlite:///{tmp_path / 'legacy.sqlite'}"
    repository = Path(__file__).parents[2]
    config = Config(str(repository / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    monkeypatch.setattr(settings, "database_url", database_url)

    command.upgrade(config, "0002")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO market_comparables "
                "(source, listing_id, cidade, preco_total, created_at) "
                "VALUES ('quintoandar', 'legacy-1', 'Old', 100000, '2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO market_comparables "
                "(source, listing_id, cidade, tipo_imovel, area_util_m2, "
                "preco_total, created_at) VALUES "
                "('quintoandar', 'legacy-1', 'New', 'APARTAMENTO', 80, "
                "400000, '2026-02-01')"
            )
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT cidade, tipo_imovel, area_util_m2, preco_total "
                "FROM market_comparables "
                "WHERE source = 'quintoandar' AND listing_id = 'legacy-1'"
            )
        ).one()
        assert row == ("New", "APARTAMENTO", 80, 400000)
        assert connection.scalar(
            text(
                "SELECT COUNT(*) FROM market_comparables "
                "WHERE source = 'quintoandar' AND listing_id = 'legacy-1'"
            )
        ) == 1

    command.downgrade(config, "0002")
    assert "opportunity_notifications" not in inspect(engine).get_table_names()
    assert "coordinate_source" not in {
        column["name"] for column in inspect(engine).get_columns("market_comparables")
    }
    command.upgrade(config, "head")
