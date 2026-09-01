from datetime import date

import pytest

from app.domain.market_stats import Sale
from app.domain.opportunities import (
    AREA_TOLERANCE,
    BAIRRO_AREA_MIN_SAMPLE,
    EXACT_MIN_SAMPLE,
    WINDOW_MONTHS,
    ListingInput,
    address_key,
    compute_opportunity,
    fingerprint,
    is_alert_eligible,
    itbi_construction_type,
    reference_date_for,
    select_reference,
    window_bounds,
)


def sale(
    *,
    neighborhood: str = "SAVASSI",
    street: str = "Rua Sao Joao",
    street_number: str | None = "10",
    settlement_date: date = date(2026, 6, 30),
    declared_value: float = 800000.0,
    built_area_acquired: float | None = 80.0,
    construction_type: str | None = "AP",
    occupation_type: str | None = "RESIDENCIAL",
) -> Sale:
    return Sale(
        neighborhood=neighborhood,
        street=street,
        street_number=street_number,
        settlement_date=settlement_date,
        declared_value=declared_value,
        built_area_acquired=built_area_acquired,
        construction_type=construction_type,
        occupation_type=occupation_type,
    )


def listing(
    *,
    tipo_imovel: str | None = "APARTAMENTO",
    area_util_m2: float | None = 80.0,
    preco_total: float | None = 500000.0,
    bairro: str | None = "Savassi",
    rua: str | None = "Rua Sao Joao",
    numero: str | None = "10",
) -> ListingInput:
    return ListingInput(
        source="quintoandar",
        listing_id="abc-1",
        tipo_imovel=tipo_imovel,
        area_util_m2=area_util_m2,
        preco_total=preco_total,
        bairro=bairro,
        rua=rua,
        numero=numero,
    )


def sales(count: int, **kwargs) -> list[Sale]:
    return [sale(**kwargs) for _ in range(count)]


def test_address_key_is_idempotent_and_accent_insensitive() -> None:
    assert address_key("SANTO AGOSTINHO") == "santo_agostinho"
    assert address_key("Santo Agostinho") == address_key("santo_agostinho")
    assert address_key("Avenida Afonso Pena") == "avenida_afonso_pena"
    assert address_key("  ") is None
    assert address_key(None) is None


def test_itbi_construction_type_maps_residential_families() -> None:
    for value in ("APARTAMENTO", "STUDIO", "KITNET", "COBERTURA", "FLAT", "LOFT"):
        assert itbi_construction_type(value) == "AP"
    assert itbi_construction_type("CASA") == "CA"
    assert itbi_construction_type("TERRENO") is None
    assert itbi_construction_type(None) is None


def test_reference_date_uses_latest_valid_residential_settlement() -> None:
    pool = [
        sale(settlement_date=date(2026, 6, 30)),
        sale(settlement_date=date(2026, 7, 15), occupation_type="COMERCIAL"),
        sale(settlement_date=date(2026, 7, 20), declared_value=0.0),
        sale(settlement_date=date(2026, 7, 25), built_area_acquired=None),
        sale(settlement_date=date(2026, 7, 28), built_area_acquired=0.0),
    ]

    assert reference_date_for(pool) == date(2026, 6, 30)


def test_reference_date_is_none_without_valid_sales() -> None:
    assert reference_date_for([]) is None
    assert reference_date_for([sale(occupation_type="COMERCIAL")]) is None


def test_window_bounds_are_inclusive_over_24_months() -> None:
    start, end = window_bounds(date(2026, 6, 30))

    assert (start, end) == (date(2024, 6, 30), date(2026, 6, 30))
    assert WINDOW_MONTHS == 24


def test_window_edges_are_included_and_older_sales_excluded() -> None:
    reference = date(2026, 6, 30)
    inside = sales(EXACT_MIN_SAMPLE - 1) + [sale(settlement_date=date(2024, 6, 30))]
    outside = [sale(settlement_date=date(2024, 6, 29))]

    result = select_reference(listing(), inside + outside, reference)

    assert result is not None
    assert result.tipo_referencia == "endereco_exato"
    assert result.amostra_count == EXACT_MIN_SAMPLE
    assert result.referencia_data_inicio == date(2024, 6, 30)
    assert result.referencia_data_fim == date(2026, 6, 30)


def test_exact_address_reference_requires_five_transactions() -> None:
    reference = date(2026, 6, 30)

    assert select_reference(listing(), sales(EXACT_MIN_SAMPLE - 1), reference).tipo_referencia != "endereco_exato"
    assert select_reference(listing(), sales(EXACT_MIN_SAMPLE), reference).tipo_referencia == "endereco_exato"


def test_exact_address_requires_street_and_number() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE)

    result = select_reference(listing(numero=None), pool, reference)

    assert result.tipo_referencia == "bairro_amplo"


def test_neighborhood_area_reference_requires_fifteen_transactions() -> None:
    reference = date(2026, 6, 30)
    pool = sales(BAIRRO_AREA_MIN_SAMPLE, street="Rua Outra", street_number="99")

    assert select_reference(listing(), pool, reference).tipo_referencia == "bairro_area"
    assert (
        select_reference(listing(), pool[:-1], reference).tipo_referencia == "bairro_amplo"
    )


def test_area_range_is_thirty_percent_around_the_listing() -> None:
    reference = date(2026, 6, 30)
    area = 80.0
    inside = [
        sale(street="Rua Outra", street_number="9", built_area_acquired=area * (1 - AREA_TOLERANCE)),
        sale(street="Rua Outra", street_number="9", built_area_acquired=area * (1 + AREA_TOLERANCE)),
    ]
    outside = [
        sale(street="Rua Outra", street_number="9", built_area_acquired=area * (1 - AREA_TOLERANCE) - 0.01),
        sale(street="Rua Outra", street_number="9", built_area_acquired=area * (1 + AREA_TOLERANCE) + 0.01),
    ]
    pool = inside * 8 + outside * 8

    result = select_reference(listing(area_util_m2=area), pool, reference)

    assert result.tipo_referencia == "bairro_area"
    assert result.amostra_count == 16


def test_broad_neighborhood_fallback_ignores_area_and_is_low_confidence() -> None:
    reference = date(2026, 6, 30)
    pool = [sale(street="Rua Outra", street_number="9", built_area_acquired=300.0)]

    result = select_reference(listing(), pool, reference)

    assert result.tipo_referencia == "bairro_amplo"
    assert result.confianca == "baixa"
    assert result.amostra_count == 1


def test_reference_never_mixes_types_or_non_residential() -> None:
    reference = date(2026, 6, 30)
    pool = (
        sales(20, construction_type="CA")
        + sales(20, occupation_type="COMERCIAL")
        + sales(20, construction_type="LO")
    )

    assert select_reference(listing(tipo_imovel="APARTAMENTO"), pool, reference) is None


def test_reference_requires_matching_neighborhood() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, neighborhood="LOURDES")

    assert select_reference(listing(bairro="Savassi"), pool, reference) is None


def test_estimated_price_uses_median_price_per_m2() -> None:
    reference = date(2026, 6, 30)
    pool = [
        sale(declared_value=800000.0, built_area_acquired=80.0),   # 10000/m2
        sale(declared_value=900000.0, built_area_acquired=90.0),   # 10000/m2
        sale(declared_value=2400000.0, built_area_acquired=80.0),  # 30000/m2 outlier
        sale(declared_value=760000.0, built_area_acquired=80.0),   # 9500/m2
        sale(declared_value=800000.0, built_area_acquired=100.0),  # 8000/m2
    ]

    result = compute_opportunity(listing(area_util_m2=80.0, preco_total=500000.0), pool, reference)

    assert result.preco_estimado == pytest.approx(800000.0)
    assert result.desconto_pct == pytest.approx(0.375)
    assert result.desconto_reais == pytest.approx(300000.0)
    assert result.confianca == "alta"
    assert result.tipo_referencia == "endereco_exato"


def test_output_values_are_rounded() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE, declared_value=812345.678, built_area_acquired=77.0)

    result = compute_opportunity(listing(area_util_m2=63.0, preco_total=500000.0), pool, reference)

    assert result.preco_estimado == round(result.preco_estimado, 2)
    assert result.desconto_reais == round(result.desconto_reais, 2)
    assert result.desconto_pct == round(result.desconto_pct, 4)


def test_negative_discount_is_reported_for_overpriced_listings() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE, declared_value=800000.0, built_area_acquired=80.0)

    result = compute_opportunity(listing(area_util_m2=80.0, preco_total=900000.0), pool, reference)

    assert result.desconto_pct == pytest.approx(-0.125)
    assert result.desconto_reais == pytest.approx(-100000.0)


def test_listing_without_area_price_or_mapped_type_has_no_opportunity() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE)

    assert compute_opportunity(listing(area_util_m2=None), pool, reference) is None
    assert compute_opportunity(listing(area_util_m2=0.0), pool, reference) is None
    assert compute_opportunity(listing(preco_total=None), pool, reference) is None
    assert compute_opportunity(listing(preco_total=0.0), pool, reference) is None
    assert compute_opportunity(listing(tipo_imovel="TERRENO"), pool, reference) is None
    assert compute_opportunity(listing(bairro=None), pool, reference) is None


def test_invalid_itbi_rows_are_excluded_from_the_sample() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE) + [
        sale(declared_value=0.0),
        sale(declared_value=-1.0),
        sale(built_area_acquired=0.0),
        sale(built_area_acquired=None),
    ]

    result = compute_opportunity(listing(), pool, reference)

    assert result.amostra_count == EXACT_MIN_SAMPLE


def test_reference_date_defaults_to_the_latest_valid_sale() -> None:
    pool = sales(EXACT_MIN_SAMPLE, settlement_date=date(2025, 5, 10))

    result = compute_opportunity(listing(), pool)

    assert result.referencia_data_fim == date(2025, 5, 10)


def test_motivos_describe_reference_sample_and_window() -> None:
    reference = date(2026, 6, 30)
    result = compute_opportunity(listing(), sales(EXACT_MIN_SAMPLE), reference)

    joined = " ".join(result.motivos)
    assert "endereço exato" in joined
    assert "5" in joined
    assert "24" in joined


def test_fingerprint_is_stable_and_sensitive_to_values() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE)
    first = compute_opportunity(listing(), pool, reference)
    again = compute_opportunity(listing(), list(reversed(pool)), reference)
    cheaper = compute_opportunity(listing(preco_total=490000.0), pool, reference)

    assert first.fingerprint == again.fingerprint
    assert first.fingerprint != cheaper.fingerprint
    assert len(first.fingerprint) == 64


def test_fingerprint_ignores_sub_cent_and_sub_basis_point_noise() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE)
    base = compute_opportunity(listing(), pool, reference)

    assert fingerprint(
        source=base.source,
        listing_id=base.listing_id,
        preco_anunciado=base.preco_anunciado + 0.0004,
        preco_estimado=base.preco_estimado + 0.0004,
        desconto_pct=base.desconto_pct + 0.000004,
        tipo_referencia=base.tipo_referencia,
        confianca=base.confianca,
        amostra_count=base.amostra_count,
        referencia_data_inicio=base.referencia_data_inicio,
        referencia_data_fim=base.referencia_data_fim,
    ) == base.fingerprint


def test_alert_eligibility_requires_discount_and_confidence() -> None:
    reference = date(2026, 6, 30)
    exact = sales(EXACT_MIN_SAMPLE, declared_value=800000.0, built_area_acquired=80.0)
    broad = [sale(street="Rua Outra", street_number="9", declared_value=800000.0, built_area_acquired=80.0)]

    strong = compute_opportunity(listing(preco_total=500000.0), exact, reference)
    weak = compute_opportunity(listing(preco_total=780000.0), exact, reference)
    low_confidence = compute_opportunity(listing(preco_total=500000.0), broad, reference)

    assert is_alert_eligible(strong) is True
    assert is_alert_eligible(weak) is False
    assert is_alert_eligible(low_confidence) is False
    assert is_alert_eligible(low_confidence, min_confianca="baixa") is True
    assert is_alert_eligible(weak, min_discount_pct=0.02) is True
