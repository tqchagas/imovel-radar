from dataclasses import replace
from datetime import datetime

DAY1 = datetime(2026, 8, 20, 9, 0)
DAY2 = datetime(2026, 8, 21, 9, 0)
DAY3 = datetime(2026, 8, 22, 9, 0)

from app.market_collectors.normalize import canonical_scope_key
from app.market_collectors.types import CollectionResult, MarketQuery, NormalizedListing
from app.models.listing_price_event import ListingPriceEvent
from app.models.market_comparable import MarketComparable
from app.services.market_refresh import refresh_market


def query(**overrides) -> MarketQuery:
    values = {"uf": "MG", "cidade": "Belo Horizonte", "bairro": "Savassi", "source": "quintoandar"}
    values.update(overrides)
    return MarketQuery(**values)


def listing(listing_id: str = "qa-1", preco: float = 500000.0) -> NormalizedListing:
    return NormalizedListing(
        source="quintoandar",
        listing_id=listing_id,
        url=f"https://www.quintoandar.com.br/imovel/{listing_id}/comprar",
        uf="MG",
        cidade="Belo Horizonte",
        bairro="Savassi",
        rua="Rua Sao Joao",
        numero="10",
        tipo_imovel="APARTAMENTO",
        area_util_m2=80.0,
        preco_total=preco,
    )


def collection(*listings, current=None, success=True, partial=False) -> CollectionResult:
    return CollectionResult(
        source="quintoandar",
        listings=list(listings),
        success=success,
        partial=partial,
        scope_key=canonical_scope_key(current or query(), "quintoandar"),
        pages=1,
    )


def events(db, listing_id: str = "qa-1") -> list[ListingPriceEvent]:
    return (
        db.query(ListingPriceEvent)
        .filter_by(listing_id=listing_id)
        .order_by(ListingPriceEvent.id)
        .all()
    )


def test_first_sight_is_recorded_as_listed(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)

    recorded = events(db_session)
    assert [item.event for item in recorded] == ["listed"]
    assert float(recorded[0].preco_total) == 500000.0
    assert recorded[0].preco_anterior is None


def test_an_unchanged_listing_records_nothing_new(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)
    refresh_market(
        db_session,
        collection(listing(), current=current),
        query=current,
        now=DAY2,
    )

    # A listing that simply keeps existing is not an event.
    assert [item.event for item in events(db_session)] == ["listed"]


def test_a_price_move_is_recorded_with_both_numbers(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)
    refresh_market(
        db_session,
        collection(listing(preco=460000.0), current=current),
        query=current,
        now=DAY2,
    )

    recorded = events(db_session)
    assert [item.event for item in recorded] == ["listed", "price_changed"]
    assert float(recorded[1].preco_anterior) == 500000.0
    assert float(recorded[1].preco_total) == 460000.0


def test_a_listing_that_stops_appearing_is_recorded_as_delisted(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)
    # An empty successful collection means the listing is gone from the portal.
    refresh_market(
        db_session,
        collection(current=current),
        query=current,
        now=DAY2,
    )

    recorded = events(db_session)
    assert [item.event for item in recorded] == ["listed", "delisted"]
    assert float(recorded[1].preco_total) == 500000.0


def test_the_score_at_the_time_travels_with_the_delisting(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)
    row = db_session.query(MarketComparable).filter_by(listing_id="qa-1").one()
    row.nota = 91
    row.desconto_pct = 0.42
    db_session.commit()

    refresh_market(
        db_session,
        collection(current=current),
        query=current,
        now=DAY2,
    )

    # This is the whole point: knowing what the model said about a listing that
    # then left the market.
    delisted = events(db_session)[-1]
    assert delisted.event == "delisted"
    assert delisted.nota == 91
    assert float(delisted.desconto_pct) == 0.42


def test_a_returning_listing_is_recorded_as_relisted(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)
    refresh_market(
        db_session, collection(current=current), query=current, now=DAY2
    )
    refresh_market(
        db_session,
        collection(listing(), current=current),
        query=current,
        now=DAY3,
    )

    assert [item.event for item in events(db_session)] == ["listed", "delisted", "relisted"]


def test_an_incomplete_collection_does_not_record_delistings(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)
    # Nothing was seen because the collection was truncated, not because the
    # listing went away.
    refresh_market(
        db_session,
        collection(current=current, success=False, partial=True),
        query=current,
        now=DAY2,
    )

    assert [item.event for item in events(db_session)] == ["listed"]


def test_both_halves_of_the_score_travel_with_the_event(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)
    row = db_session.query(MarketComparable).filter_by(listing_id="qa-1").one()
    row.nota, row.nota_itbi, row.nota_qpreco = 26, 91, 26
    row.desconto_pct = 0.42
    db_session.commit()

    refresh_market(db_session, collection(current=current), query=current, now=DAY2)

    # A nota final sozinha não distingue "nunca foi candidato" de "era candidato
    # e o qpreço vetou" — e é essa diferença que a análise de desfecho precisa
    # medir. Gravar depois é impossível: o estado já passou.
    delisted = events(db_session)[-1]
    assert delisted.nota == 26
    assert delisted.nota_itbi == 91
    assert delisted.nota_qpreco == 26


def test_the_score_halves_travel_with_a_price_move(db_session):
    current = query()
    refresh_market(db_session, collection(listing(), current=current), query=current, now=DAY1)
    row = db_session.query(MarketComparable).filter_by(listing_id="qa-1").one()
    row.nota, row.nota_itbi, row.nota_qpreco = 88, 88, None
    db_session.commit()

    refresh_market(
        db_session,
        collection(listing(preco=450000.0), current=current),
        query=current,
        now=DAY2,
    )

    moved = events(db_session)[-1]
    assert moved.event == "price_changed"
    assert moved.nota_itbi == 88
    assert moved.nota_qpreco is None
