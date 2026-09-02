from dataclasses import replace
from datetime import date

import pytest

from app.market_collectors.types import MarketQuery
from app.models.transaction import Transaction
from app.services import market_coverage
from app.services.market_coverage import neighborhoods_with_itbi, sweep_city

CITY = "belo_horizonte"


def transaction(db, *, index: int, neighborhood: str, settlement_date=date(2026, 6, 30)):
    db.add(
        Transaction(
            city=CITY,
            source_row_hash=f"h-{neighborhood}-{index}",
            raw_address="Rua X, 1",
            street="Rua X",
            street_number="1",
            neighborhood=neighborhood,
            built_area_acquired=80.0,
            construction_type="AP",
            occupation_type="RESIDENCIAL",
            declared_value=800000.0,
            calc_base_value=800000.0,
            settlement_date=settlement_date,
        )
    )


def seed(db, counts: dict[str, int]) -> None:
    for neighborhood, count in counts.items():
        for index in range(count):
            transaction(db, index=index, neighborhood=neighborhood)
    db.flush()


def query(**overrides) -> MarketQuery:
    values = {"uf": "MG", "cidade": "Belo Horizonte", "source": "quintoandar"}
    values.update(overrides)
    return MarketQuery(**values)


def test_only_neighborhoods_with_enough_itbi_are_swept(db_session):
    seed(db_session, {"SAVASSI": 40, "LOURDES": 35, "VILA VAZIA": 5})

    names = neighborhoods_with_itbi(db_session, "Belo Horizonte", min_sales=30)

    # A neighborhood with no transactions cannot be scored, so collecting it
    # would only add listings that never surface.
    assert set(names) == {"SAVASSI", "LOURDES"}


def test_neighborhoods_are_ordered_by_itbi_volume(db_session):
    seed(db_session, {"SAVASSI": 40, "LOURDES": 90})

    assert neighborhoods_with_itbi(db_session, "Belo Horizonte", min_sales=30)[0] == "LOURDES"


def test_stale_transactions_do_not_qualify_a_neighborhood(db_session):
    seed(db_session, {"SAVASSI": 40})
    for index in range(40):
        transaction(db_session, index=index, neighborhood="ANTIGO", settlement_date=date(2019, 1, 1))
    db_session.flush()

    assert "ANTIGO" not in neighborhoods_with_itbi(db_session, "Belo Horizonte", min_sales=30)


def test_sweep_visits_each_neighborhood_once(db_session, monkeypatch):
    seen = []

    def fake(db, scoped, deactivate=True):
        seen.append((scoped.bairros, scoped.quartos))
        return {"status": "success", "seen": 10, "scope_key": "k"}

    monkeypatch.setattr(market_coverage, "collect_and_refresh", fake)
    report = sweep_city(db_session, query(), neighborhoods=["Savassi", "Lourdes"])

    assert [item[0] for item in seen] == [("Savassi",), ("Lourdes",)]
    assert report["collected"] == 2
    assert report["capped"] == 0
    assert report["seen"] == 20


def test_a_capped_scope_is_split_by_bedrooms(db_session, monkeypatch):
    calls = []

    def fake(db, scoped, deactivate=True):
        calls.append(scoped.quartos)
        # The whole-neighborhood scope is truncated; the per-bedroom ones fit.
        status = "partial" if scoped.quartos is None else "success"
        return {"status": status, "seen": 5, "scope_key": "k"}

    monkeypatch.setattr(market_coverage, "collect_and_refresh", fake)
    report = sweep_city(db_session, query(), neighborhoods=["Savassi"])

    assert calls == [None, *market_coverage.BEDROOM_SPLITS]
    assert report["capped"] == 0
    assert report["collected"] == len(market_coverage.BEDROOM_SPLITS)


def test_splitting_can_be_turned_off(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        market_coverage,
        "collect_and_refresh",
        lambda db, scoped, deactivate=True: (
            calls.append(scoped.quartos) or {"status": "partial", "seen": 1, "scope_key": "k"}
        ),
    )
    report = sweep_city(db_session, query(), neighborhoods=["Savassi"], split_on_cap=False)

    assert calls == [None]
    assert report["capped"] == 1


def test_one_failing_neighborhood_does_not_stop_the_sweep(db_session, monkeypatch):
    def fake(db, scoped, deactivate=True):
        if scoped.bairros == ("Lourdes",):
            raise RuntimeError("gateway caiu")
        return {"status": "success", "seen": 7, "scope_key": "k"}

    monkeypatch.setattr(market_coverage, "collect_and_refresh", fake)
    report = sweep_city(db_session, query(), neighborhoods=["Savassi", "Lourdes", "Sion"])

    assert report["failed"] == 1
    assert report["collected"] == 2
    assert report["seen"] == 14


def test_sweep_keeps_the_query_filters(db_session, monkeypatch):
    captured = []
    monkeypatch.setattr(
        market_coverage,
        "collect_and_refresh",
        lambda db, scoped, deactivate=True: (
            captured.append(scoped) or {"status": "success", "seen": 1, "scope_key": "k"}
        ),
    )
    sweep_city(db_session, query(tipo_imovel="APARTAMENTO", max_pages=7), neighborhoods=["Savassi"])

    assert captured[0].tipo_imovel == "APARTAMENTO"
    assert captured[0].max_pages == 7
    assert captured[0].source == "quintoandar"


def comparable(db, *, source: str, bairro: str, listing_id: str):
    from app.domain.slugs import address_key
    from app.models.market_comparable import MarketComparable

    db.add(
        MarketComparable(
            source=source,
            listing_id=listing_id,
            cidade="Belo Horizonte",
            bairro=bairro,
            cidade_normalizada=CITY,
            bairro_normalizado=address_key(bairro),
            ativo=True,
        )
    )
    db.flush()


def test_itbi_names_are_translated_to_the_spelling_portals_answer_to(db_session, monkeypatch):
    # VivaReal matches addressNeighborhood exactly: "Santo Antônio" returns
    # thousands of listings, "SANTO ANTONIO" returns zero and a 200.
    comparable(db_session, source="vivareal", bairro="Santo Antônio", listing_id="vr-1")
    asked = []
    monkeypatch.setattr(
        market_coverage,
        "collect_and_refresh",
        lambda db, scoped, deactivate=True: (
            asked.append(scoped.bairros[0]) or {"status": "success", "seen": 3, "scope_key": "k"}
        ),
    )

    sweep_city(db_session, query(source="vivareal"), neighborhoods=["SANTO ANTONIO"])

    assert asked == ["Santo Antônio"]


def test_a_name_learned_from_one_portal_serves_the_others(db_session, monkeypatch):
    # Loft and QuintoAndar are case and accent insensitive, so they collect the
    # neighborhood first and record its proper spelling for VivaReal to reuse.
    comparable(db_session, source="loft", bairro="Funcionários", listing_id="lf-1")
    asked = []
    monkeypatch.setattr(
        market_coverage,
        "collect_and_refresh",
        lambda db, scoped, deactivate=True: (
            asked.append(scoped.bairros[0]) or {"status": "success", "seen": 1, "scope_key": "k"}
        ),
    )

    sweep_city(db_session, query(source="vivareal"), neighborhoods=["FUNCIONARIOS"])

    assert asked == ["Funcionários"]


def test_the_sources_own_spelling_wins_when_both_are_known(db_session, monkeypatch):
    comparable(db_session, source="loft", bairro="Sion Loft", listing_id="lf-2")
    comparable(db_session, source="vivareal", bairro="Sion Loft", listing_id="vr-2")
    names = market_coverage.canonical_neighborhoods(db_session, "vivareal", "Belo Horizonte")

    assert names["sion_loft"] == "Sion Loft"


def test_an_unknown_name_falls_back_to_the_itbi_spelling(db_session, monkeypatch):
    asked = []
    monkeypatch.setattr(
        market_coverage,
        "collect_and_refresh",
        lambda db, scoped, deactivate=True: (
            asked.append(scoped.bairros[0]) or {"status": "success", "seen": 1, "scope_key": "k"}
        ),
    )

    sweep_city(db_session, query(), neighborhoods=["NOVO BAIRRO"])

    assert asked == ["NOVO BAIRRO"]


def test_a_scope_that_returns_nothing_is_not_counted_as_collected(db_session, monkeypatch):
    # This is how a mismatched name looks from the outside: HTTP 200, zero rows.
    # Counting it as success is how a sweep reports covering a city it never
    # touched.
    monkeypatch.setattr(
        market_coverage,
        "collect_and_refresh",
        lambda db, scoped, deactivate=True: {"status": "success", "seen": 0, "scope_key": "k"},
    )

    report = sweep_city(db_session, query(), neighborhoods=["SAVASSI"], split_on_cap=False)

    assert report["empty"] == 1
    assert report["collected"] == 0
