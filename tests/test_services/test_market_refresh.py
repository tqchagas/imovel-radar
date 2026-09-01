import json
from datetime import datetime, timezone

from app.market_collectors.types import CollectionResult, MarketQuery, NormalizedListing
from app.models.market_comparable import MarketComparable
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

    refresh_market(db_session, result(listing("a-1")), now=datetime(2026, 8, 31, tzinfo=timezone.utc))
    refresh_market(db_session, result(listing("a-1")), now=datetime(2026, 9, 1, tzinfo=timezone.utc))

    saved = db_session.query(MarketComparable).one()
    assert saved.first_seen_at == first_seen.replace(tzinfo=None)
    assert saved.last_seen_at == datetime(2026, 9, 1)
    assert saved.url.endswith("/a-1/comprar")
    assert db_session.query(MarketComparable).count() == 1


def test_refresh_normalizes_address_and_records_scope(db_session) -> None:
    refresh_market(db_session, result(listing("a-2", rua="Rua São João"), scope_key="scope-canonical"))

    saved = db_session.query(MarketComparable).one()
    assert saved.cidade_normalizada == "belo_horizonte"
    assert saved.bairro_normalizado == "savassi"
    assert saved.rua_normalizada == "rua_sao_joao"
    assert saved.numero_normalizado == "10"
    assert saved.collection_scope_key == "scope-canonical"


def test_scope_key_is_canonical_and_all_neighborhoods_are_distinct() -> None:
    all_neighborhoods = canonical_scope_key(
        source="quintoandar", uf="mg", cidade="Belo Horizonte", bairros=[], filtros={"quartos": 2}
    )
    reordered = canonical_scope_key(
        source="QUINTOANDAR", uf=" MG ", cidade="Belo Horizonte", bairros=["Savassi", "Centro"], filtros={"quartos": 2}
    )
    same_reordered = canonical_scope_key(
        source="quintoandar", uf="MG", cidade="Belo Horizonte", bairros=["Centro", "Savassi"], filtros={"quartos": 2}
    )

    assert all_neighborhoods != reordered
    assert reordered == same_reordered
    payload = json.loads(reordered.split(":", 1)[1])
    assert payload["bairros"] == ["Centro", "Savassi"]
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
    refresh_market(db_session, result(listing("same"), scope_key="scope-1"))

    assert db_session.query(MarketComparable).filter_by(listing_id="same", source="quintoandar").one().ativo is True
    assert db_session.query(MarketComparable).filter_by(listing_id="missing", source="quintoandar").one().ativo is False
    assert db_session.query(MarketComparable).filter_by(listing_id="other-scope", source="quintoandar").one().ativo is True
    assert db_session.query(MarketComparable).filter_by(listing_id="missing", source="vivareal").one().ativo is True


def test_failed_or_partial_collection_does_not_deactivate(db_session) -> None:
    db_session.add(MarketComparable(source="quintoandar", listing_id="existing", ativo=True, collection_scope_key="scope-1"))
    db_session.commit()

    refresh_market(db_session, result(scope_key="scope-1", success=False), deactivate=True)
    refresh_market(db_session, result(scope_key="scope-1", partial=True), deactivate=True)

    assert db_session.query(MarketComparable).one().ativo is True
