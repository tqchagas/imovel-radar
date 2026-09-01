from datetime import date, datetime, timezone

import pytest

from app.domain.opportunities import EXACT_MIN_SAMPLE
from app.models.market_comparable import MarketComparable
from app.models.transaction import Transaction
from app.services.opportunities import (
    fetch_reference_sales,
    latest_reference_date,
    refresh_opportunities,
)

CITY = "belo_horizonte"


def transaction(
    db,
    *,
    index: int,
    neighborhood: str = "SAVASSI",
    street: str = "Rua Sao Joao",
    street_number: str | None = "10",
    settlement_date: date = date(2026, 6, 30),
    declared_value: float = 800000.0,
    built_area_acquired: float | None = 80.0,
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


def seed_exact_sample(db, count: int = EXACT_MIN_SAMPLE, **kwargs) -> None:
    for index in range(count):
        transaction(db, index=index, **kwargs)


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
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY)

    db_session.refresh(listing)
    assert float(listing.preco_estimado) == pytest.approx(800000.0)
    assert float(listing.desconto_pct) == pytest.approx(0.375)
    assert float(listing.desconto_reais) == pytest.approx(300000.0)
    assert listing.tipo_referencia == "endereco_exato"
    assert listing.confianca == "alta"
    assert listing.amostra_count == EXACT_MIN_SAMPLE
    assert listing.referencia_data_inicio == date(2026, 6, 30)
    assert listing.referencia_data_fim == date(2026, 6, 30)
    assert "endereço exato" in listing.oportunidade_motivo
    assert len(listing.oportunidade_fingerprint) == 64
    assert summary["calculated"] == 1
    assert summary["alta"] == 1
    assert summary["eligible"] == 1
    assert summary["reference_date"] == date(2026, 6, 30)


def test_refresh_is_idempotent(db_session) -> None:
    seed_exact_sample(db_session)
    listing = comparable(db_session)
    db_session.flush()

    refresh_opportunities(db_session, city=CITY)
    db_session.refresh(listing)
    first = listing.oportunidade_fingerprint

    refresh_opportunities(db_session, city=CITY)
    db_session.refresh(listing)

    assert listing.oportunidade_fingerprint == first


def test_low_confidence_is_materialized_without_alert_fingerprint(db_session) -> None:
    transaction(db_session, index=1, street="Rua Outra", street_number="99")
    listing = comparable(db_session)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY)

    db_session.refresh(listing)
    assert listing.tipo_referencia == "bairro_amplo"
    assert listing.confianca == "baixa"
    assert float(listing.preco_estimado) == pytest.approx(800000.0)
    assert listing.oportunidade_fingerprint is None
    assert summary["baixa"] == 1
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

    summary = refresh_opportunities(db_session, city=CITY)

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

    summary = refresh_opportunities(db_session, city=CITY)

    db_session.refresh(inactive)
    assert inactive.preco_estimado is None
    assert summary["listings"] == 0


def test_refresh_can_be_scoped_to_a_single_source(db_session) -> None:
    seed_exact_sample(db_session)
    quintoandar = comparable(db_session, listing_id="qa-1", source="quintoandar")
    vivareal = comparable(db_session, listing_id="vr-1", source="vivareal")
    db_session.flush()

    refresh_opportunities(db_session, city=CITY, source="vivareal")

    db_session.refresh(quintoandar)
    db_session.refresh(vivareal)
    assert quintoandar.preco_estimado is None
    assert vivareal.preco_estimado is not None


def test_refresh_without_itbi_data_leaves_listings_untouched(db_session) -> None:
    listing = comparable(db_session)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY)

    db_session.refresh(listing)
    assert listing.preco_estimado is None
    assert summary["reference_date"] is None
    assert summary["calculated"] == 0


def test_refresh_ignores_listings_without_area_or_price(db_session) -> None:
    seed_exact_sample(db_session)
    no_area = comparable(db_session, listing_id="no-area", area_util_m2=None)
    no_price = comparable(db_session, listing_id="no-price", preco_total=None)
    db_session.flush()

    summary = refresh_opportunities(db_session, city=CITY)

    db_session.refresh(no_area)
    db_session.refresh(no_price)
    assert no_area.preco_estimado is None
    assert no_price.preco_estimado is None
    assert summary["calculated"] == 0
    assert summary["cleared"] == 2
