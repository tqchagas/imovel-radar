import json
from datetime import datetime, timezone

import pytest

from app.market_collectors.normalize import canonical_scope_key as collector_scope_key
from app.market_collectors.types import CollectionResult, MarketQuery, NormalizedListing
from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import CollectionRun
from app.services.market_refresh import canonical_scope_key, refresh_market


def listing(listing_id: str, *, bairro: str = "Savassi", rua: str = "Rua Sao Joao") -> NormalizedListing:
    return NormalizedListing(
        source="quintoandar",
        listing_id=listing_id,
        url=f"https://www.quintoandar.com.br/imovel/{listing_id}/comprar",
        uf="MG",
        cidade="Belo Horizonte",
        bairro=bairro,
        rua=rua,
        numero="10",
        tipo_imovel="APARTAMENTO",
        area_util_m2=80,
        preco_total=400000,
    )


def result(*listings: NormalizedListing, scope_key: str = "scope-1", success: bool = True, partial: bool = False) -> CollectionResult:
    return CollectionResult(
        source="quintoandar",
        listings=list(listings),
        success=success,
        partial=partial,
        scope_key=scope_key,
        pages=1,
        error=None if success else "collector error",
    )


def query() -> MarketQuery:
    return MarketQuery(uf="MG", cidade="Belo Horizonte", bairro="Savassi", source="quintoandar")


def test_upsert_is_idempotent_and_preserves_first_seen(db_session) -> None:
    first_seen = datetime(2026, 8, 1, tzinfo=timezone.utc)
    db_session.add(
        MarketComparable(
            source="quintoandar",
            listing_id="a-1",
            first_seen_at=first_seen,
            last_seen_at=first_seen,
        )
    )
    db_session.commit()

    refresh_market(db_session, result(listing("a-1")), now=datetime(2026, 8, 31, tzinfo=timezone.utc), query=query())
    refresh_market(db_session, result(listing("a-1")), now=datetime(2026, 9, 1, tzinfo=timezone.utc), query=query())

    saved = db_session.query(MarketComparable).one()
    assert saved.first_seen_at == first_seen.replace(tzinfo=None)
    assert saved.last_seen_at == datetime(2026, 9, 1)
    assert saved.url.endswith("/a-1/comprar")
    assert db_session.query(MarketComparable).count() == 1


def test_refresh_normalizes_address_and_records_scope(db_session) -> None:
    refresh_market(db_session, result(listing("a-2", rua="Rua São João"), scope_key="scope-canonical"), query=query())

    saved = db_session.query(MarketComparable).one()
    assert saved.cidade_normalizada == "belo_horizonte"
    assert saved.bairro_normalizado == "savassi"
    assert saved.rua_normalizada == "rua_sao_joao"
    assert saved.numero_normalizado == "10"
    assert saved.collection_scope_key == "scope-canonical"


def test_scope_key_is_canonical_and_all_neighborhoods_are_distinct() -> None:
    all_neighborhoods = canonical_scope_key(
        MarketQuery(uf="mg", cidade="Belo Horizonte", quartos=2), "quintoandar"
    )
    reordered = canonical_scope_key(
        MarketQuery(uf=" MG ", cidade="Belo Horizonte", bairros=("Savassi", "Centro"), quartos=2),
        "QUINTOANDAR",
    )
    same_reordered = canonical_scope_key(
        MarketQuery(uf="MG", cidade="Belo Horizonte", bairros=("Centro", "Savassi"), quartos=2),
        "quintoandar",
    )

    assert all_neighborhoods != reordered
    assert reordered == same_reordered
    payload = json.loads(reordered.split(":", 1)[1])
    assert payload["bairros"] == ["Centro", "Savassi"]
    assert payload["filtros"] == {"quartos": 2}
    assert list(payload) == ["bairros", "cidade", "filtros", "source", "uf"]


def test_seen_listing_is_reactivated_and_missing_listing_is_deactivated_only_in_same_scope(db_session) -> None:
    db_session.add_all(
        [
            MarketComparable(source="quintoandar", listing_id="same", ativo=True, collection_scope_key="scope-1"),
            MarketComparable(source="quintoandar", listing_id="missing", ativo=True, collection_scope_key="scope-1"),
            MarketComparable(source="quintoandar", listing_id="other-scope", ativo=True, collection_scope_key="scope-2"),
            MarketComparable(source="vivareal", listing_id="missing", ativo=True, collection_scope_key="scope-1"),
        ]
    )
    db_session.commit()

    db_session.query(MarketComparable).filter_by(listing_id="same", source="quintoandar").one().ativo = False
    refresh_market(db_session, result(listing("same"), scope_key="scope-1"), query=query())

    assert db_session.query(MarketComparable).filter_by(listing_id="same", source="quintoandar").one().ativo is True
    assert db_session.query(MarketComparable).filter_by(listing_id="same", source="quintoandar").one().activation_event_id == 2
    assert db_session.query(MarketComparable).filter_by(listing_id="missing", source="quintoandar").one().ativo is False
    assert db_session.query(MarketComparable).filter_by(listing_id="other-scope", source="quintoandar").one().ativo is True
    assert db_session.query(MarketComparable).filter_by(listing_id="missing", source="vivareal").one().ativo is True


def test_failed_or_partial_collection_does_not_deactivate(db_session) -> None:
    db_session.add(MarketComparable(source="quintoandar", listing_id="existing", ativo=True, collection_scope_key="scope-1"))
    db_session.commit()

    refresh_market(db_session, result(scope_key="scope-1", success=False), deactivate=True, query=query())
    refresh_market(db_session, result(scope_key="scope-1", partial=True), deactivate=True, query=query())

    assert db_session.query(MarketComparable).one().ativo is True


def test_collection_run_persists_exact_query_scope(db_session) -> None:
    query = MarketQuery(
        uf=" MG ",
        cidade="Belo Horizonte",
        bairro="Savassi",
        tipo_imovel="APARTAMENTO",
        quartos=2,
        area_util_m2=70,
        max_pages=3,
        source="quintoandar",
    )
    scope = canonical_scope_key(query, "quintoandar")

    refresh_market(
        db_session,
        result(listing("a-3"), scope_key=scope),
        query=query,
    )

    run = db_session.query(CollectionRun).one()
    assert run.uf == "MG"
    assert run.cidade == "Belo Horizonte"
    assert run.bairros_json == '["Savassi"]'
    assert run.filtros_json == '{"area_util_m2":70,"quartos":2,"tipo_imovel":"APARTAMENTO"}'
    assert run.scope_key == scope


def test_upsert_conflict_is_safe_across_sessions(tmp_path) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.base import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'refresh.sqlite'}")
    Base.metadata.create_all(engine)
    collection = result(listing("concurrent"))
    # SQLite serializes writers; this verifies the native conflict path, not a
    # deterministic interleaving of concurrent writers.
    with Session(engine) as first, Session(engine) as second:
        refresh_market(first, collection, query=query())
        refresh_market(second, collection, query=query())

    with Session(engine) as db:
        assert db.query(MarketComparable).filter_by(listing_id="concurrent").count() == 1


def test_refresh_requires_query_before_writing_run(db_session) -> None:
    with pytest.raises(ValueError, match="query is required"):
        refresh_market(db_session, result(listing("missing-query")))

    assert db_session.query(CollectionRun).count() == 0


def test_collectors_and_refresh_use_the_same_scope_key_function() -> None:
    current = query()
    assert canonical_scope_key is collector_scope_key
    assert canonical_scope_key(current, "quintoandar") == collector_scope_key(current, "quintoandar")
