import json
from datetime import date, datetime

from app.ingestion.cli import run_opportunity_alerts
from app.market_collectors.normalize import canonical_scope_key
from app.market_collectors.types import CollectionResult, MarketQuery, NormalizedListing
from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import OpportunityAlertConfig, OpportunityNotification
from app.models.transaction import Transaction
from app.services import market_refresh as refresh_module

NOW = datetime(2026, 8, 20, 9, 0)
RECIPIENTS = ["alerta@example.com"]


class Recorder:
    def __init__(self) -> None:
        self.messages = []

    def __call__(self, message) -> None:
        self.messages.append(message)


def itbi(index: int) -> Transaction:
    return Transaction(
        city="belo_horizonte",
        source_row_hash=f"hash-{index}",
        raw_address="Rua Sao Joao, 10",
        street="Rua Sao Joao",
        street_number="10",
        neighborhood="SAVASSI",
        built_area_acquired=80.0,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        declared_value=800000.0,
        calc_base_value=800000.0,
        settlement_date=date(2026, 6, 30),
    )


def normalized(source: str, listing_id: str, preco: float) -> NormalizedListing:
    return NormalizedListing(
        source=source,
        listing_id=listing_id,
        url=f"https://example.com/{listing_id}",
        uf="MG",
        cidade="Belo Horizonte",
        bairro="Savassi",
        rua="Rua Sao Joao",
        numero="10",
        tipo_imovel="APARTAMENTO",
        area_util_m2=80.0,
        preco_total=preco,
    )


def collector(source: str, listings, *, success: bool = True, partial: bool = False):
    def collect(query: MarketQuery) -> CollectionResult:
        return CollectionResult(
            source=source,
            listings=list(listings),
            success=success,
            partial=partial,
            scope_key=canonical_scope_key(query, source),
            pages=1,
            error=None if success else "collector error",
        )

    return collect


def seed(db) -> None:
    for index in range(6):
        db.add(itbi(index))
    db.add(
        OpportunityAlertConfig(
            cidade="belo_horizonte",
            bairros_json="[]",
            desconto_minimo_pct=0.15,
            confianca_minima="media",
            destinatarios_json=json.dumps(RECIPIENTS),
            periodicidade_minutos=720,
        )
    )
    db.add(
        MarketComparable(
            source="vivareal",
            listing_id="vr-antigo",
            url="https://example.com/vr-antigo",
            cidade="Belo Horizonte",
            bairro="Savassi",
            rua="Rua Sao Joao",
            numero="10",
            cidade_normalizada="belo_horizonte",
            bairro_normalizado="savassi",
            rua_normalizada="rua_sao_joao",
            numero_normalizado="10",
            tipo_imovel="APARTAMENTO",
            area_util_m2=80.0,
            preco_total=700000.0,
            ativo=True,
            collection_scope_key=canonical_scope_key(
                MarketQuery(uf="MG", cidade="Belo Horizonte", bairro="Savassi", source="vivareal"),
                "vivareal",
            ),
            first_seen_at=datetime(2026, 8, 1),
            last_seen_at=datetime(2026, 8, 19),
        )
    )
    db.commit()


def test_partial_source_does_not_block_the_other_source(monkeypatch, db_session) -> None:
    seed(db_session)
    monkeypatch.setitem(
        refresh_module.COLLECTORS,
        "quintoandar",
        collector("quintoandar", [normalized("quintoandar", "qa-1", 500000.0)]),
    )
    monkeypatch.setitem(
        refresh_module.COLLECTORS,
        "vivareal",
        collector("vivareal", [], success=False, partial=True),
    )
    sender = Recorder()

    summary = run_opportunity_alerts(
        db_session,
        cidade="Belo Horizonte",
        uf="MG",
        bairros=["Savassi"],
        sources=["quintoandar", "vivareal"],
        sender=sender,
        now=NOW,
    )

    collections = {item["source"]: item for item in summary["collections"]}
    assert collections["quintoandar"]["status"] == "success"
    assert collections["vivareal"]["status"] == "partial"

    # The partial source keeps its listings: nothing is deactivated on a degraded run.
    kept = db_session.query(MarketComparable).filter_by(listing_id="vr-antigo").one()
    assert kept.ativo is True

    collected = db_session.query(MarketComparable).filter_by(listing_id="qa-1").one()
    assert float(collected.preco_estimado) == 800000.0
    assert collected.confianca == "alta"

    assert summary["opportunities"]["calculated"] == 2
    assert summary["alerts"]["sent"] == 1
    assert len(sender.messages) == 1
    assert "qa-1" in sender.messages[0].body


def test_only_eligible_opportunities_are_emailed(monkeypatch, db_session) -> None:
    seed(db_session)
    monkeypatch.setitem(
        refresh_module.COLLECTORS,
        "quintoandar",
        collector(
            "quintoandar",
            [
                normalized("quintoandar", "qa-1", 500000.0),
                normalized("quintoandar", "qa-caro", 790000.0),
            ],
        ),
    )
    monkeypatch.setitem(refresh_module.COLLECTORS, "vivareal", collector("vivareal", []))
    sender = Recorder()

    summary = run_opportunity_alerts(
        db_session,
        cidade="Belo Horizonte",
        uf="MG",
        bairros=["Savassi"],
        sources=["quintoandar", "vivareal"],
        sender=sender,
        now=NOW,
    )

    assert summary["alerts"]["sent"] == 1
    alerted = db_session.query(OpportunityNotification).all()
    assert len(alerted) == 1
    expensive = db_session.query(MarketComparable).filter_by(listing_id="qa-caro").one()
    assert expensive.oportunidade_fingerprint is None

    # A successful vivareal run with no listings deactivates only its own scope.
    kept = db_session.query(MarketComparable).filter_by(listing_id="vr-antigo").one()
    assert kept.ativo is False


def test_dry_run_calculates_without_sending(monkeypatch, db_session) -> None:
    seed(db_session)
    monkeypatch.setitem(
        refresh_module.COLLECTORS,
        "quintoandar",
        collector("quintoandar", [normalized("quintoandar", "qa-1", 500000.0)]),
    )
    monkeypatch.setitem(refresh_module.COLLECTORS, "vivareal", collector("vivareal", []))
    sender = Recorder()

    summary = run_opportunity_alerts(
        db_session,
        cidade="Belo Horizonte",
        uf="MG",
        bairros=["Savassi"],
        sources=["quintoandar", "vivareal"],
        sender=sender,
        now=NOW,
        dry_run=True,
    )

    assert summary["alerts"]["eligible"] == 1
    assert summary["alerts"]["sent"] == 0
    assert sender.messages == []
    assert db_session.query(OpportunityNotification).count() == 0


def test_missing_configuration_stops_the_job_before_collecting(monkeypatch, db_session) -> None:
    calls = []

    def collect(query: MarketQuery) -> CollectionResult:
        calls.append(query.source)
        raise AssertionError("collector must not run without configuration")

    monkeypatch.setitem(refresh_module.COLLECTORS, "quintoandar", collect)

    summary = run_opportunity_alerts(
        db_session,
        cidade="Belo Horizonte",
        uf="MG",
        bairros=["Savassi"],
        sources=["quintoandar"],
        sender=Recorder(),
        now=NOW,
    )

    assert summary["status"] == "disabled"
    assert calls == []
