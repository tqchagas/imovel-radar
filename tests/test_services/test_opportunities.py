from datetime import date, datetime, timezone

import pytest

from app.domain.opportunities import EXACT_MIN_SAMPLE, MIN_SCORE
from app.models.market_comparable import MarketComparable
from app.models.transaction import Transaction
from app.core.http_client import PortalBlocked
from app.services.opportunities import (
    QPRECO_MAX_CONSECUTIVE_FAILURES,
    fetch_reference_sales,
    latest_reference_date,
    refresh_opportunities,
)

CITY = "belo_horizonte"

# These fixtures are deliberately minimal: they exercise the service plumbing,
# not the statistics behind the calibration factor.
TINY = {"min_calibration_listings": 1, "min_calibration_sales": 1}


def transaction(
    db,
    *,
    index: int,
    neighborhood: str = "SAVASSI",
    street: str = "Rua Sao Joao",
    street_number: str | None = "10",
    settlement_date: date = date(2026, 6, 30),
    declared_value: float = 1280000.0,
    built_area_acquired: float | None = 128.0,
    construction_type: str | None = "AP",
    occupation_type: str | None = "RESIDENCIAL",
    city: str = CITY,
) -> Transaction:
    row = Transaction(
        city=city,
        source_row_hash=f"hash-{index}",
        raw_address=f"{street}, {street_number}",
        street=street,
        street_number=street_number,
        neighborhood=neighborhood,
        built_area_acquired=built_area_acquired,
        construction_type=construction_type,
        occupation_type=occupation_type,
        declared_value=declared_value,
        calc_base_value=declared_value,
        settlement_date=settlement_date,
    )
    db.add(row)
    return row


def comparable(
    db,
    *,
    listing_id: str = "abc-1",
    source: str = "quintoandar",
    ativo: bool = True,
    cidade: str = "Belo Horizonte",
    bairro: str = "Savassi",
    rua: str = "Rua Sao Joao",
    numero: str = "10",
    tipo_imovel: str = "APARTAMENTO",
    area_util_m2: float | None = 80.0,
    preco_total: float | None = 500000.0,
) -> MarketComparable:
    row = MarketComparable(
        source=source,
        listing_id=listing_id,
        url=f"https://example.com/{listing_id}",
        cidade=cidade,
        bairro=bairro,
        rua=rua,
        numero=numero,
        cidade_normalizada=cidade.lower().replace(" ", "_"),
        bairro_normalizado=bairro.lower().replace(" ", "_"),
        rua_normalizada=rua.lower().replace(" ", "_"),
        numero_normalizado=numero,
        tipo_imovel=tipo_imovel,
        area_util_m2=area_util_m2,
        preco_total=preco_total,
        ativo=ativo,
        first_seen_at=datetime(2026, 8, 1),
        last_seen_at=datetime(2026, 8, 20),
    )
    db.add(row)
    return row


# Enough rows for the score to measure the sample's spread instead of assuming
# the worst; the alert floor is deliberately out of reach for thinner samples.
SCORABLE_SAMPLE = 20


def seed_exact_sample(db, count: int = SCORABLE_SAMPLE, **kwargs) -> None:
    for index in range(count):
        transaction(db, index=index, **kwargs)


def seed_peer_listings(db, count: int = 4, preco_total: float = 800000.0) -> None:
    """Listings asking exactly the ITBI median, so the measured calibration
    factor lands on 1.0 and the arithmetic under test stays readable.

    Without peers the factor is measured from the single listing being scored,
    which collapses the estimate onto that listing's own price."""
    for index in range(count):
        comparable(db, listing_id=f"peer-{index}", preco_total=preco_total)


def test_latest_reference_date_ignores_invalid_and_other_cities(db_session) -> None:
    transaction(db_session, index=1, settlement_date=date(2026, 6, 30))
    transaction(db_session, index=2, settlement_date=date(2026, 7, 10), occupation_type="COMERCIAL")
    transaction(db_session, index=3, settlement_date=date(2026, 7, 11), declared_value=0.0)
    transaction(db_session, index=4, settlement_date=date(2026, 7, 12), built_area_acquired=None)
    transaction(db_session, index=5, settlement_date=date(2026, 8, 1), city="contagem")
    db_session.flush()

    assert latest_reference_date(db_session, CITY) == date(2026, 6, 30)
    assert latest_reference_date(db_session, "Belo Horizonte") == date(2026, 6, 30)
    assert latest_reference_date(db_session, "uberlandia") is None


def test_fetch_reference_sales_filters_window_city_and_validity(db_session) -> None:
    transaction(db_session, index=1, settlement_date=date(2026, 6, 30))
    transaction(db_session, index=2, settlement_date=date(2024, 6, 30))
    transaction(db_session, index=3, settlement_date=date(2024, 6, 29))
    transaction(db_session, index=4, settlement_date=date(2026, 6, 1), occupation_type="COMERCIAL")
    transaction(db_session, index=5, settlement_date=date(2026, 6, 1), city="contagem")
    db_session.flush()

    sales = fetch_reference_sales(db_session, CITY, date(2024, 6, 30), date(2026, 6, 30))

    assert sorted(sale.settlement_date for sale in sales) == [date(2024, 6, 30), date(2026, 6, 30)]


def test_refresh_materializes_opportunity_fields(db_session) -> None:
    seed_exact_sample(db_session)
    listing = comparable(db_session)
    seed_peer_listings(db_session)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(listing)
    assert float(listing.preco_estimado) == pytest.approx(800000.0)
    assert float(listing.desconto_pct) == pytest.approx(0.375)
    assert float(listing.desconto_reais) == pytest.approx(300000.0)
    assert listing.tipo_referencia == "endereco_exato"
    assert listing.confianca == "alta"
    assert listing.amostra_count == SCORABLE_SAMPLE
    assert listing.referencia_data_inicio == date(2026, 6, 30)
    assert listing.referencia_data_fim == date(2026, 6, 30)
    assert "endereço exato" in listing.oportunidade_motivo
    assert len(listing.oportunidade_fingerprint) == 64
    assert summary["calculated"] == 5
    assert summary["alta"] == 5
    # Only the cheap listing clears the discount floor; the peers sit at parity.
    assert summary["eligible"] == 1
    assert summary["reference_date"] == date(2026, 6, 30)


def test_refresh_is_idempotent(db_session) -> None:
    seed_exact_sample(db_session)
    listing = comparable(db_session)
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, **TINY)
    db_session.refresh(listing)
    first = listing.oportunidade_fingerprint

    refresh_opportunities(db_session, city=CITY, **TINY)
    db_session.refresh(listing)

    assert listing.oportunidade_fingerprint == first


def test_low_confidence_is_materialized_without_alert_fingerprint(db_session) -> None:
    transaction(db_session, index=1, street="Rua Outra", street_number="99")
    listing = comparable(db_session)
    seed_peer_listings(db_session)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(listing)
    assert listing.tipo_referencia == "bairro_amplo"
    assert listing.confianca == "baixa"
    assert float(listing.preco_estimado) == pytest.approx(800000.0)
    assert listing.oportunidade_fingerprint is None
    assert summary["baixa"] == 5
    assert summary["eligible"] == 0


def test_refresh_clears_stale_values_when_no_reference_exists(db_session) -> None:
    seed_exact_sample(db_session)
    listing = comparable(db_session, bairro="Lourdes")
    db_session.flush()
    listing.preco_estimado = 123.0
    listing.desconto_pct = 0.5
    listing.confianca = "alta"
    listing.oportunidade_fingerprint = "stale"
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(listing)
    assert listing.preco_estimado is None
    assert listing.desconto_pct is None
    assert listing.confianca is None
    assert listing.oportunidade_fingerprint is None
    assert summary["cleared"] == 1


def test_refresh_skips_inactive_listings(db_session) -> None:
    seed_exact_sample(db_session)
    inactive = comparable(db_session, listing_id="gone", ativo=False)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(inactive)
    assert inactive.preco_estimado is None
    assert summary["listings"] == 0


def test_refresh_can_be_scoped_to_a_single_source(db_session) -> None:
    seed_exact_sample(db_session)
    quintoandar = comparable(db_session, listing_id="qa-1", source="quintoandar")
    vivareal = comparable(db_session, listing_id="vr-1", source="vivareal")
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, **TINY, source="vivareal")

    db_session.refresh(quintoandar)
    db_session.refresh(vivareal)
    assert quintoandar.preco_estimado is None
    assert vivareal.preco_estimado is not None


def test_refresh_without_itbi_data_leaves_listings_untouched(db_session) -> None:
    listing = comparable(db_session)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(listing)
    assert listing.preco_estimado is None
    assert summary["reference_date"] is None
    assert summary["calculated"] == 0


def test_refresh_ignores_listings_without_area_or_price(db_session) -> None:
    seed_exact_sample(db_session)
    no_area = comparable(db_session, listing_id="no-area", area_util_m2=None)
    no_price = comparable(db_session, listing_id="no-price", preco_total=None)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(no_area)
    db_session.refresh(no_price)
    assert no_area.preco_estimado is None
    assert no_price.preco_estimado is None
    assert summary["calculated"] == 0
    assert summary["cleared"] == 2


def test_same_unit_from_two_sources_alerts_once(db_session) -> None:
    seed_exact_sample(db_session)
    seed_peer_listings(db_session)
    # The same flat carried by two portals: same street, number, area and price.
    vivareal = comparable(db_session, listing_id="vr-1", source="vivareal", preco_total=500000.0)
    loft = comparable(db_session, listing_id="lf-1", source="loft", preco_total=500000.0)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(vivareal)
    db_session.refresh(loft)
    baselines = [vivareal.oportunidade_fingerprint, loft.oportunidade_fingerprint]
    # Both keep their opportunity, but only one carries the alert baseline.
    assert vivareal.preco_estimado is not None and loft.preco_estimado is not None
    assert sum(1 for value in baselines if value is not None) == 1
    assert summary["duplicates"] == 1
    assert summary["eligible"] == 1


def test_the_deepest_discount_wins_the_duplicated_unit(db_session) -> None:
    seed_exact_sample(db_session)
    seed_peer_listings(db_session)
    # Same flat, same asking price, areas that round to the same 80 m2 - the
    # slightly larger one is the better buy.
    smaller = comparable(db_session, listing_id="menor", source="vivareal", area_util_m2=79.6)
    larger = comparable(db_session, listing_id="maior", source="loft", area_util_m2=80.4)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(smaller)
    db_session.refresh(larger)
    assert larger.oportunidade_fingerprint is not None
    assert smaller.oportunidade_fingerprint is None
    assert summary["duplicates"] == 1


def test_different_units_are_not_deduplicated(db_session) -> None:
    seed_exact_sample(db_session)
    seed_peer_listings(db_session)
    first = comparable(db_session, listing_id="a", source="vivareal", preco_total=500000.0)
    # A different flat in the same building: same address, different size, but
    # inside the same calibration band so the factor still comes from its peers.
    second = comparable(db_session, listing_id="b", source="loft", preco_total=500000.0, area_util_m2=85.0)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(first)
    db_session.refresh(second)
    assert first.oportunidade_fingerprint is not None
    assert second.oportunidade_fingerprint is not None
    assert summary["duplicates"] == 0


# --- qpreço -------------------------------------------------------------------


def with_suggestion(
    row: MarketComparable,
    *,
    preco_sugerido: float = 700000.0,
    banda_pct: float = 0.10,
    updated_at: datetime | None = datetime(2026, 8, 20, tzinfo=timezone.utc),
) -> MarketComparable:
    row.price_suggestion_json = "{}"
    row.price_suggestion_price = preco_sugerido
    row.price_suggestion_lower_bound = preco_sugerido * (1 - banda_pct)
    row.price_suggestion_upper_bound = preco_sugerido * (1 + banda_pct)
    row.price_suggestion_updated_at = updated_at
    return row


def fake_fetcher(calls: list[str], *, preco_sugerido: float = 510000.0, fails: set | None = None):
    """Stands in for the QuintoAndar call: writes what the real one writes."""

    def fetch(row: MarketComparable) -> bool:
        calls.append(row.listing_id)
        if fails and row.listing_id in fails:
            raise RuntimeError("http_503")
        with_suggestion(row, preco_sugerido=preco_sugerido, updated_at=NOW)
        return True

    return fetch


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_refresh_persists_a_qpreco_already_stored(db_session) -> None:
    seed_exact_sample(db_session)
    listing = with_suggestion(comparable(db_session), preco_sugerido=510000.0)
    seed_peer_listings(db_session)
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(listing)
    assert float(listing.qpreco_desconto_pct) == pytest.approx(0.0196, abs=0.0001)
    # ITBI alone would alert on this listing; QuintoAndar sees no discount at
    # all, so the lower of the two scores is what is kept.
    assert listing.nota_itbi >= MIN_SCORE
    assert listing.nota == listing.nota_qpreco < MIN_SCORE
    assert listing.oportunidade_fingerprint is None


def test_refresh_fetches_the_qpreco_only_for_alertable_quintoandar_listings(db_session) -> None:
    seed_exact_sample(db_session)
    cheap = comparable(db_session, listing_id="cheap")
    comparable(db_session, listing_id="parity", preco_total=800000.0)
    comparable(db_session, listing_id="cheap-loft", source="loft")
    seed_peer_listings(db_session)
    db_session.flush()
    calls: list[str] = []

    summary = refresh_opportunities(
        db_session, city=CITY, qpreco_fetcher=fake_fetcher(calls), now=NOW, **TINY
    )

    assert calls == ["cheap"]
    assert summary["qpreco_buscados"] == 1
    assert summary["qpreco_falhas"] == 0
    db_session.refresh(cheap)
    assert float(cheap.price_suggestion_price) == pytest.approx(510000.0)


def test_a_fetched_qpreco_is_scored_in_the_same_run(db_session) -> None:
    seed_exact_sample(db_session)
    listing = comparable(db_session)
    seed_peer_listings(db_session)
    db_session.flush()

    refresh_opportunities(
        db_session, city=CITY, qpreco_fetcher=fake_fetcher([]), now=NOW, **TINY
    )

    db_session.refresh(listing)
    assert listing.nota_qpreco < MIN_SCORE
    assert listing.nota == listing.nota_qpreco


def test_a_fresh_qpreco_is_not_fetched_again(db_session) -> None:
    seed_exact_sample(db_session)
    with_suggestion(
        comparable(db_session), preco_sugerido=900000.0, updated_at=datetime(2026, 8, 20)
    )
    seed_peer_listings(db_session)
    db_session.flush()
    calls: list[str] = []

    refresh_opportunities(
        db_session, city=CITY, qpreco_fetcher=fake_fetcher(calls), now=NOW, **TINY
    )

    assert calls == []


def test_a_stale_qpreco_is_refetched(db_session) -> None:
    seed_exact_sample(db_session)
    with_suggestion(
        comparable(db_session), preco_sugerido=900000.0, updated_at=datetime(2026, 1, 1)
    )
    seed_peer_listings(db_session)
    db_session.flush()
    calls: list[str] = []

    refresh_opportunities(
        db_session, city=CITY, qpreco_fetcher=fake_fetcher(calls), now=NOW, **TINY
    )

    assert calls == ["abc-1"]


def test_the_qpreco_fetch_honours_its_budget(db_session) -> None:
    seed_exact_sample(db_session)
    for index in range(5):
        comparable(db_session, listing_id=f"cheap-{index}", preco_total=500000.0 - index)
    # Enough listings at parity that the five cheap ones do not drag the
    # calibration factor down to their own price.
    seed_peer_listings(db_session, count=15)
    db_session.flush()
    calls: list[str] = []

    refresh_opportunities(
        db_session,
        city=CITY,
        qpreco_fetcher=fake_fetcher(calls),
        qpreco_limit=2,
        now=NOW,
        **TINY,
    )

    assert len(calls) == 2


def test_one_failing_qpreco_does_not_stop_the_others(db_session) -> None:
    seed_exact_sample(db_session)
    comparable(db_session, listing_id="broken")
    survivor = comparable(db_session, listing_id="ok", preco_total=500001.0)
    seed_peer_listings(db_session)
    db_session.flush()
    calls: list[str] = []

    summary = refresh_opportunities(
        db_session,
        city=CITY,
        qpreco_fetcher=fake_fetcher(calls, fails={"broken"}),
        now=NOW,
        **TINY,
    )

    assert sorted(calls) == ["broken", "ok"]
    assert summary["qpreco_buscados"] == 1
    assert summary["qpreco_falhas"] == 1
    db_session.refresh(survivor)
    assert survivor.nota_qpreco < MIN_SCORE


def test_refresh_without_a_fetcher_never_calls_quintoandar(db_session) -> None:
    seed_exact_sample(db_session)
    listing = comparable(db_session)
    seed_peer_listings(db_session)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(listing)
    assert listing.nota_qpreco is None
    assert listing.qpreco_desconto_pct is None
    assert summary["qpreco_buscados"] == 0


def test_a_block_stops_the_qpreco_step_at_once(db_session) -> None:
    seed_exact_sample(db_session)
    for index in range(5):
        comparable(db_session, listing_id=f"cheap-{index}", preco_total=500000.0 - index)
    seed_peer_listings(db_session, count=15)
    db_session.flush()
    calls: list[str] = []

    def blocked(row: MarketComparable) -> bool:
        calls.append(row.listing_id)
        raise PortalBlocked("http_429")

    summary = refresh_opportunities(
        db_session, city=CITY, qpreco_fetcher=blocked, now=NOW, **TINY
    )

    # Being refused once is the portal saying stop; spending the rest of the
    # budget against it is what turns a throttle into a ban.
    assert len(calls) == 1
    assert summary["qpreco_interrompido"] == "bloqueado"
    assert summary["qpreco_falhas"] == 1


def test_repeated_errors_stop_the_qpreco_step(db_session) -> None:
    seed_exact_sample(db_session)
    for index in range(6):
        comparable(db_session, listing_id=f"cheap-{index}", preco_total=500000.0 - index)
    seed_peer_listings(db_session, count=15)
    db_session.flush()
    calls: list[str] = []

    def always_fails(row: MarketComparable) -> bool:
        calls.append(row.listing_id)
        raise RuntimeError("http_500")

    summary = refresh_opportunities(
        db_session, city=CITY, qpreco_fetcher=always_fails, now=NOW, **TINY
    )

    assert len(calls) == QPRECO_MAX_CONSECUTIVE_FAILURES
    assert summary["qpreco_interrompido"] == "falhas_seguidas"


def test_an_isolated_error_does_not_stop_the_qpreco_step(db_session) -> None:
    seed_exact_sample(db_session)
    for index in range(4):
        comparable(db_session, listing_id=f"cheap-{index}", preco_total=500000.0 - index)
    seed_peer_listings(db_session, count=15)
    db_session.flush()
    calls: list[str] = []
    fetch = fake_fetcher(calls, fails={"cheap-0"})

    summary = refresh_opportunities(
        db_session, city=CITY, qpreco_fetcher=fetch, now=NOW, **TINY
    )

    assert len(calls) == 4
    assert summary["qpreco_interrompido"] is None
    assert summary["qpreco_buscados"] == 3


# --- área lida da descrição não vira alerta -----------------------------------


def test_a_parsed_area_is_scored_but_never_alerted(db_session) -> None:
    seed_exact_sample(db_session)
    lido = comparable(db_session, listing_id="lido", source="loft", preco_total=500000.0)
    lido.area_origem = "descricao"
    seed_peer_listings(db_session, count=15)
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(lido)
    # A área do texto discorda da publicada em ~13% dos casos, e o erro puxa
    # para baixo — o que faria o anúncio parecer barato. Ele aparece na tela
    # com estimativa, mas não dispara alerta.
    assert lido.preco_estimado is not None
    assert lido.nota is not None
    assert lido.oportunidade_fingerprint is None


def test_a_parsed_area_does_not_move_the_calibration(db_session) -> None:
    seed_exact_sample(db_session)
    # Vinte anúncios ao preço da mediana do ITBI fixam o fator em 1,0. Outros
    # vinte e um, com área lida do texto e metade do tamanho, pedem o dobro por
    # m² — se entrassem na conta, a mediana do fator iria para 2,0.
    seed_peer_listings(db_session, count=20)
    for indice in range(21):
        torto = comparable(db_session, listing_id=f"torto-{indice}", source="loft",
                           area_util_m2=80.0, preco_total=1600000.0)
        torto.area_origem = "descricao"
    alvo = comparable(db_session, listing_id="alvo", preco_total=500000.0)
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(alvo)
    assert float(alvo.fator_calibracao) == pytest.approx(1.0, abs=0.01)


# --- contexto de vizinhança (similares) ---------------------------------------


def test_the_similares_step_covers_every_source(db_session) -> None:
    seed_exact_sample(db_session)
    # O endpoint localiza pela coordenada; sem ela não há o que perguntar.
    for listing_id, source, preco in (("lo-1", "loft", 500000.0), ("vr-1", "vivareal", 500001.0)):
        row = comparable(db_session, listing_id=listing_id, source=source, preco_total=preco)
        row.lat, row.lon = -19.93, -43.93
    seed_peer_listings(db_session, count=15)
    db_session.flush()
    chamados: list[str] = []

    def buscar(row: MarketComparable) -> bool:
        chamados.append(row.listing_id)
        row.similares_m2_anunciado = 9000.0
        row.similares_dias_ate_negocio = 119
        row.similares_updated_at = NOW
        return True

    summary = refresh_opportunities(
        db_session, city=CITY, similares_fetcher=buscar, now=NOW, **TINY
    )

    # Ao contrário do qpreço, que só existe para o QuintoAndar, este endpoint
    # pergunta por coordenada e responde para qualquer fonte.
    assert sorted(chamados) == ["lo-1", "vr-1"]
    assert summary["similares_buscados"] == 2


def test_the_similares_do_not_move_the_score(db_session) -> None:
    seed_exact_sample(db_session)
    alvo = comparable(db_session, listing_id="lo-1", source="loft")
    alvo.lat, alvo.lon = -19.93, -43.93
    seed_peer_listings(db_session, count=15)
    db_session.flush()

    sem = refresh_opportunities(db_session, city=CITY, **TINY)
    db_session.refresh(alvo)
    nota_sem = alvo.nota

    def buscar(row: MarketComparable) -> bool:
        # Metade do preço por m² da vizinhança: se isso entrasse na nota, ela
        # despencaria. É contexto, não avaliação da unidade.
        row.similares_m2_anunciado = 1000.0
        row.similares_updated_at = NOW
        return True

    refresh_opportunities(db_session, city=CITY, similares_fetcher=buscar, now=NOW, **TINY)

    db_session.refresh(alvo)
    assert alvo.nota == nota_sem
    assert float(alvo.similares_m2_anunciado) == 1000.0


def test_a_fresh_similares_reading_is_not_fetched_again(db_session) -> None:
    seed_exact_sample(db_session)
    row = comparable(db_session, listing_id="lo-1", source="loft")
    row.lat, row.lon = -19.93, -43.93
    row.similares_updated_at = datetime(2026, 8, 20)
    seed_peer_listings(db_session, count=15)
    db_session.flush()
    chamados: list[str] = []

    refresh_opportunities(
        db_session, city=CITY, now=NOW, **TINY,
        similares_fetcher=lambda r: chamados.append(r.listing_id) or True,
    )

    assert chamados == []


# --- régua emprestada dos vizinhos --------------------------------------------


def test_a_loft_listing_borrows_the_qpreco_of_its_street(db_session) -> None:
    seed_exact_sample(db_session)
    # Três anúncios do QuintoAndar na mesma rua e faixa de área, com qpreço.
    for indice in range(3):
        vizinho = comparable(db_session, listing_id=f"qa-{indice}", preco_total=900000.0)
        vizinho.price_suggestion_price = 800000.0  # 10.000/m² em 80 m²
        vizinho.price_suggestion_updated_at = NOW
    alvo = comparable(db_session, listing_id="lo-1", source="loft", preco_total=500000.0)
    seed_peer_listings(db_session, count=15)
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(alvo)
    # O Loft nunca terá qpreço próprio; a mediana dos vizinhos erra 6,7% contra
    # os 22,2% da escada de ITBI.
    assert alvo.referencia_primaria == "qpreco_vizinho"
    assert float(alvo.preco_estimado) == pytest.approx(800000.0)


def test_a_listing_alone_on_its_street_keeps_the_itbi_reference(db_session) -> None:
    seed_exact_sample(db_session)
    sozinho = comparable(db_session, listing_id="lo-1", source="loft", preco_total=500000.0)
    seed_peer_listings(db_session, count=15)
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(sozinho)
    assert sozinho.referencia_primaria == "itbi"


def test_one_neighbour_is_not_enough_to_borrow_from(db_session) -> None:
    seed_exact_sample(db_session)
    unico = comparable(db_session, listing_id="qa-0", preco_total=900000.0)
    unico.price_suggestion_price = 800000.0
    alvo = comparable(db_session, listing_id="lo-1", source="loft", preco_total=500000.0)
    seed_peer_listings(db_session, count=15)
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, **TINY)

    db_session.refresh(alvo)
    # Um vizinho é anedota: sem par para medir dispersão, não há régua.
    assert alvo.referencia_primaria == "itbi"
