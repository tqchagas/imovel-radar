from datetime import date

import pytest

from app.domain.market_stats import Sale
from app.domain.opportunities import (
    AREA_MATCH_FACTOR,
    HOMOGENEOUS_BUILDING_DISPERSION,
    SCORE_BANDS,
    SCORE_FULL_SIGNAL,
    score_band,
    score_band_label,
    AREA_TOLERANCE,
    itbi_area_for,
    BAIRRO_AREA_MIN_SAMPLE,
    EXACT_MIN_SAMPLE,
    MIN_SCORE,
    STREET_MIN_SAMPLE,
    WINDOW_MONTHS,
    Calibration,
    ListingInput,
    NeighbourEstimate,
    PriceSuggestion,
    SaleIndex,
    build_calibration,
    unit_fingerprint,
    address_key,
    compute_opportunity,
    expected_error,
    fingerprint,
    is_alert_eligible,
    itbi_construction_type,
    reference_date_for,
    score,
    select_reference,
    window_bounds,
)


# Compares against the raw ITBI median, so the arithmetic below stays readable.
FLAT = Calibration.flat(1.0)


def sale(
    *,
    neighborhood: str = "SAVASSI",
    street: str = "Rua Sao Joao",
    street_number: str | None = "10",
    settlement_date: date = date(2026, 6, 30),
    declared_value: float = 1280000.0,
    built_area_acquired: float | None = 128.0,
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
    qpreco=None,
    qpreco_vizinhos=None,
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
        qpreco=qpreco,
        qpreco_vizinhos=qpreco_vizinhos,
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


def test_exact_address_reference_requires_its_sample_floor() -> None:
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


def test_area_range_is_thirty_percent_around_the_converted_area() -> None:
    reference = date(2026, 6, 30)
    area = 80.0
    esperada = itbi_area_for(area)
    inside = [
        sale(street="Rua Outra", street_number="9", built_area_acquired=esperada * (1 - AREA_TOLERANCE)),
        sale(street="Rua Outra", street_number="9", built_area_acquired=esperada * (1 + AREA_TOLERANCE)),
    ]
    outside = [
        sale(street="Rua Outra", street_number="9", built_area_acquired=esperada * (1 - AREA_TOLERANCE) - 0.01),
        sale(street="Rua Outra", street_number="9", built_area_acquired=esperada * (1 + AREA_TOLERANCE) + 0.01),
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
        sale(declared_value=1280000.0, built_area_acquired=128.0),   # 10000/m2
        sale(declared_value=1440000.0, built_area_acquired=144.0),   # 10000/m2
        sale(declared_value=3840000.0, built_area_acquired=128.0),  # 30000/m2 outlier
        sale(declared_value=1216000.0, built_area_acquired=128.0),   # 9500/m2
        sale(declared_value=1280000.0, built_area_acquired=160.0),  # 8000/m2
    ]

    result = compute_opportunity(listing(area_util_m2=80.0, preco_total=500000.0), pool, reference, FLAT)

    assert result.preco_estimado == pytest.approx(800000.0)
    assert result.desconto_pct == pytest.approx(0.375)
    assert result.desconto_reais == pytest.approx(300000.0)
    assert result.confianca == "alta"
    assert result.tipo_referencia == "endereco_exato"


def test_output_values_are_rounded() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE, declared_value=1299753.08, built_area_acquired=123.2)

    result = compute_opportunity(listing(area_util_m2=63.0, preco_total=500000.0), pool, reference, FLAT)

    assert result.preco_estimado == round(result.preco_estimado, 2)
    assert result.desconto_reais == round(result.desconto_reais, 2)
    assert result.desconto_pct == round(result.desconto_pct, 4)


def test_negative_discount_is_reported_for_overpriced_listings() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE, declared_value=1280000.0, built_area_acquired=128.0)

    result = compute_opportunity(listing(area_util_m2=80.0, preco_total=900000.0), pool, reference, FLAT)

    assert result.desconto_pct == pytest.approx(-0.125)
    assert result.desconto_reais == pytest.approx(-100000.0)


def test_listing_without_area_price_or_mapped_type_has_no_opportunity() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE)

    assert compute_opportunity(listing(area_util_m2=None), pool, reference, FLAT) is None
    assert compute_opportunity(listing(area_util_m2=0.0), pool, reference, FLAT) is None
    assert compute_opportunity(listing(preco_total=None), pool, reference, FLAT) is None
    assert compute_opportunity(listing(preco_total=0.0), pool, reference, FLAT) is None
    assert compute_opportunity(listing(tipo_imovel="TERRENO"), pool, reference, FLAT) is None
    assert compute_opportunity(listing(bairro=None), pool, reference, FLAT) is None


def test_invalid_itbi_rows_are_excluded_from_the_sample() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE) + [
        sale(declared_value=0.0),
        sale(declared_value=-1.0),
        sale(built_area_acquired=0.0),
        sale(built_area_acquired=None),
    ]

    result = compute_opportunity(listing(), pool, reference, FLAT)

    assert result.amostra_count == EXACT_MIN_SAMPLE


def test_reference_date_defaults_to_the_latest_valid_sale() -> None:
    pool = sales(EXACT_MIN_SAMPLE, settlement_date=date(2025, 5, 10))

    result = compute_opportunity(listing(), pool, None, FLAT)

    assert result.referencia_data_fim == date(2025, 5, 10)


def test_motivos_describe_reference_sample_and_window() -> None:
    reference = date(2026, 6, 30)
    result = compute_opportunity(listing(), sales(EXACT_MIN_SAMPLE), reference, FLAT)

    joined = " ".join(result.motivos)
    assert "endereço exato" in joined
    assert str(EXACT_MIN_SAMPLE) in joined
    assert str(WINDOW_MONTHS) in joined


def test_fingerprint_is_stable_and_sensitive_to_values() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE)
    first = compute_opportunity(listing(), pool, reference, FLAT)
    again = compute_opportunity(listing(), list(reversed(pool)), reference, FLAT)
    cheaper = compute_opportunity(listing(preco_total=490000.0), pool, reference, FLAT)

    assert first.fingerprint == again.fingerprint
    assert first.fingerprint != cheaper.fingerprint
    assert len(first.fingerprint) == 64


def test_fingerprint_ignores_sub_cent_and_sub_basis_point_noise() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE)
    base = compute_opportunity(listing(), pool, reference, FLAT)

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


def test_alert_eligibility_is_gated_by_the_score() -> None:
    reference = date(2026, 6, 30)
    # Twenty sales at the same address: enough for the score to measure the
    # spread rather than assume the worst.
    exact = sales(20, declared_value=1280000.0, built_area_acquired=128.0)
    thin = sales(EXACT_MIN_SAMPLE, declared_value=1280000.0, built_area_acquired=128.0)

    strong = compute_opportunity(listing(preco_total=500000.0), exact, reference, FLAT)
    weak = compute_opportunity(listing(preco_total=780000.0), exact, reference, FLAT)
    thin_sample = compute_opportunity(listing(preco_total=500000.0), thin, reference, FLAT)

    assert strong.nota >= MIN_SCORE
    assert is_alert_eligible(strong) is True
    # A small discount scores low however good the sample is.
    assert is_alert_eligible(weak) is False
    # A amostra rasa recebe a dispersão pessimista de 35%, então o mesmo
    # desconto fica abaixo do piso de alerta. Mas ela não é esmagada: pontua 72
    # e não zero, porque na validação cruzada uma referência de endereço exato
    # com menos de 4 linhas erra 11,9% — pior que uma amostra funda, melhor que
    # a rua que a substituiria.
    assert thin_sample.nota < strong.nota
    assert is_alert_eligible(thin_sample) is False
    assert thin_sample.nota > MIN_SCORE // 2


def test_score_rewards_a_tight_sample_over_a_loose_one() -> None:
    reference = date(2026, 6, 30)
    tight = [
        sale(declared_value=800000.0 + offset, built_area_acquired=80.0)
        for offset in range(-10000, 10000, 1000)
    ]
    loose = [
        sale(declared_value=800000.0 + offset, built_area_acquired=80.0)
        for offset in range(-400000, 400000, 40000)
    ]

    firm = compute_opportunity(listing(preco_total=500000.0), tight, reference, FLAT)
    vague = compute_opportunity(listing(preco_total=500000.0), loose, reference, FLAT)

    # Same discount, same sample size: only the spread of the reference differs.
    assert firm.desconto_pct == pytest.approx(vague.desconto_pct, abs=0.02)
    assert firm.nota > vague.nota


def test_an_implausible_discount_scores_lower_than_a_credible_one() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    credible = compute_opportunity(listing(preco_total=480000.0), pool, reference, FLAT)
    absurd = compute_opportunity(listing(preco_total=120000.0), pool, reference, FLAT)

    # An 85% discount is nearly always a wrong area or a mislabelled unit, so
    # the curve turns back down instead of rewarding it.
    assert absurd.desconto_pct > credible.desconto_pct
    assert absurd.nota < credible.nota


# --- escada de referência por rua -------------------------------------------


def test_street_reference_sits_between_exact_address_and_neighborhood() -> None:
    reference = date(2026, 6, 30)
    # Same street, different buildings: too few per address for the exact tier.
    pool = [sale(street_number=str(100 + i)) for i in range(STREET_MIN_SAMPLE)]

    result = select_reference(listing(numero="999"), pool, reference)

    assert result.tipo_referencia == "rua"
    assert result.confianca == "media"
    assert result.amostra_count == STREET_MIN_SAMPLE


def test_street_reference_requires_its_own_sample_floor() -> None:
    reference = date(2026, 6, 30)
    pool = [sale(street_number=str(100 + i)) for i in range(STREET_MIN_SAMPLE - 1)]

    assert select_reference(listing(numero="999"), pool, reference).tipo_referencia != "rua"


def test_exact_address_still_wins_over_the_street() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE) + [sale(street_number=str(100 + i)) for i in range(STREET_MIN_SAMPLE)]

    assert select_reference(listing(), pool, reference).tipo_referencia == "endereco_exato"


def test_neighborhood_tiers_are_low_confidence() -> None:
    reference = date(2026, 6, 30)
    area_pool = sales(BAIRRO_AREA_MIN_SAMPLE, street="Rua Outra", street_number="99")
    broad_pool = [sale(street="Rua Outra", street_number="9", built_area_acquired=300.0)]

    # Filtering by area band barely narrows the ITBI spread, so neither
    # neighborhood tier is trusted enough to raise an alert.
    assert select_reference(listing(), area_pool, reference).confianca == "baixa"
    assert select_reference(listing(), broad_pool, reference).confianca == "baixa"


# --- calibração --------------------------------------------------------------


def test_calibration_converts_the_itbi_median_into_an_asking_price() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE, declared_value=1280000.0, built_area_acquired=128.0)

    raw = compute_opportunity(listing(preco_total=800000.0), pool, reference, FLAT)
    calibrated = compute_opportunity(
        listing(preco_total=800000.0), pool, reference, Calibration.flat(2.0)
    )

    assert raw.preco_estimado == pytest.approx(800000.0)
    assert calibrated.preco_estimado == pytest.approx(1600000.0)
    assert calibrated.fator_calibracao == pytest.approx(2.0)
    # Same listing, same ITBI: only the factor decides whether it is a bargain.
    assert raw.desconto_pct == pytest.approx(0.0)
    assert calibrated.desconto_pct == pytest.approx(0.5)


def test_listing_without_a_measurable_factor_is_not_an_opportunity() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE)

    # An uncalibrated estimate is the failure mode this module exists to avoid:
    # it must yield nothing rather than fall back to a neutral factor.
    assert compute_opportunity(listing(), pool, reference, Calibration()) is None


def test_calibration_is_measured_per_neighborhood_and_size_band() -> None:
    reference = date(2026, 6, 30)
    pool = sales(40, street="Rua Outra", street_number="9", declared_value=1280000.0, built_area_acquired=128.0)
    index = SaleIndex.build(pool, reference)
    # 20 listings asking 16000/m2 where the ITBI median is 10000/m2.
    listings = [
        ListingInput(
            source="vivareal",
            listing_id=f"v{i}",
            tipo_imovel="APARTAMENTO",
            area_util_m2=80.0,
            preco_total=1280000.0,
            bairro="Savassi",
            rua="Rua Sao Joao",
            numero="10",
        )
        for i in range(20)
    ]

    calibration = build_calibration(listings, index)

    assert calibration.factor("AP", "savassi", 80.0) == pytest.approx(1.6)
    # Nothing measured for houses, so nothing is claimed.
    assert calibration.factor("CA", "savassi", 80.0) is None


def test_calibration_ignores_scopes_without_enough_evidence() -> None:
    reference = date(2026, 6, 30)
    index = SaleIndex.build(sales(40, built_area_acquired=80.0), reference)
    few = [
        ListingInput(
            source="loft",
            listing_id=f"l{i}",
            tipo_imovel="APARTAMENTO",
            area_util_m2=80.0,
            preco_total=1280000.0,
            bairro="Savassi",
            rua="Rua Sao Joao",
            numero="10",
        )
        for i in range(3)
    ]

    assert build_calibration(few, index).factor("AP", "savassi", 80.0) is None


# --- índice de vendas --------------------------------------------------------


def test_sale_index_matches_scanning_the_raw_sale_list() -> None:
    reference = date(2026, 6, 30)
    pool = sales(EXACT_MIN_SAMPLE) + sales(5, neighborhood="LOURDES")

    from_list = select_reference(listing(), pool, reference)
    from_index = select_reference(listing(), SaleIndex.build(pool, reference), reference)

    assert from_index == from_list


def test_sale_index_drops_rows_outside_the_window_and_the_invalid_ones() -> None:
    reference = date(2026, 6, 30)
    pool = [
        sale(),
        sale(settlement_date=date(2024, 6, 29)),
        sale(occupation_type="COMERCIAL"),
        sale(built_area_acquired=None),
    ]

    index = SaleIndex.build(pool, reference)

    assert len(index.by_neighborhood[("AP", "savassi")]) == 1


# --- identidade da unidade ---------------------------------------------------


def test_unit_fingerprint_matches_the_same_flat_across_sources() -> None:
    vivareal = listing()
    # QuintoAndar and Loft never publish a street number, so the key must match
    # across the gap or cross-portal duplicates never collapse.
    loft = ListingInput(
        source="loft",
        listing_id="outro-id",
        tipo_imovel="APARTAMENTO",
        area_util_m2=80.0,
        preco_total=500000.0,
        bairro="Savassi",
        rua="Rua Sao Joao",
        numero=None,
    )

    assert unit_fingerprint(vivareal) == unit_fingerprint(loft)


def test_unit_fingerprint_separates_different_flats() -> None:
    base = listing()

    assert unit_fingerprint(base) != unit_fingerprint(listing(rua="Rua Outra"))
    assert unit_fingerprint(base) != unit_fingerprint(listing(area_util_m2=95.0))
    assert unit_fingerprint(base) != unit_fingerprint(listing(preco_total=600000.0))
    # Sub-thousand price noise is the same unit re-advertised.
    assert unit_fingerprint(base) == unit_fingerprint(listing(preco_total=500400.0))


def test_unit_fingerprint_needs_a_street_and_a_neighborhood() -> None:
    assert unit_fingerprint(listing(rua=None)) is None
    assert unit_fingerprint(listing(bairro=None)) is None


def test_calibration_is_measured_against_each_listings_own_reference() -> None:
    reference = date(2026, 6, 30)
    # The street is denser and pricier than the neighborhood around it. A factor
    # taken against the neighborhood median would over-inflate the estimate for
    # anything scored at the street tier.
    street = [
        sale(street_number=str(100 + i), declared_value=1920000.0, built_area_acquired=128.0)
        for i in range(20)
    ]
    elsewhere = [
        sale(street="Rua Barata", street_number=str(i), declared_value=1280000.0, built_area_acquired=128.0)
        for i in range(40)
    ]
    index = SaleIndex.build(street + elsewhere, reference)
    on_street = [
        ListingInput(
            source="vivareal",
            listing_id=f"s{i}",
            tipo_imovel="APARTAMENTO",
            area_util_m2=80.0,
            preco_total=2400000.0,
            bairro="Savassi",
            rua="Rua Sao Joao",
            numero="999",
        )
        for i in range(20)
    ]

    calibration = build_calibration(on_street, index)

    # Asking 30000/m2 against a street reference of 15000/m2 is a factor of 2,
    # not the 3.75 a neighborhood-median calibration would have produced.
    assert calibration.factor("AP", "savassi", 80.0) == pytest.approx(2.0)


def test_a_typical_listing_shows_no_discount_against_its_peers() -> None:
    reference = date(2026, 6, 30)
    pool = sales(40, street_number="99", declared_value=1280000.0, built_area_acquired=128.0)
    index = SaleIndex.build(pool, reference)
    peers = [
        ListingInput(
            source="loft",
            listing_id=f"p{i}",
            tipo_imovel="APARTAMENTO",
            area_util_m2=80.0,
            preco_total=1600000.0,
            bairro="Savassi",
            rua="Rua Sao Joao",
            numero="10",
        )
        for i in range(20)
    ]

    calibration = build_calibration(peers, index)
    typical = compute_opportunity(peers[0], index, reference, calibration)

    # The whole point of the calibration: the median listing is not a bargain.
    assert typical.desconto_pct == pytest.approx(0.0, abs=0.01)
    assert typical.nota == 0


# --- qpreço (sugestão de preço do QuintoAndar) --------------------------------


def suggestion(
    *,
    preco_sugerido: float = 700000.0,
    limite_inferior: float | None = 630000.0,
    limite_superior: float | None = 770000.0,
) -> PriceSuggestion:
    return PriceSuggestion(
        preco_sugerido=preco_sugerido,
        limite_inferior=limite_inferior,
        limite_superior=limite_superior,
    )


def test_a_listing_without_a_qpreco_scores_exactly_as_before() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    plain = compute_opportunity(listing(preco_total=500000.0), pool, reference, FLAT)

    assert plain.qpreco_estimado is None
    assert plain.qpreco_desconto_pct is None
    assert plain.nota_qpreco is None
    assert plain.nota == plain.nota_itbi


def test_a_disagreeing_qpreco_pulls_the_score_down() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)
    # The ITBI says the flat is worth 800k and it asks 500k; QuintoAndar says
    # it is worth 510k, so there is no bargain to alert about.
    disagreeing = listing(preco_total=500000.0, qpreco=suggestion(preco_sugerido=510000.0))

    itbi_only = compute_opportunity(listing(preco_total=500000.0), pool, reference, FLAT)
    combined = compute_opportunity(disagreeing, pool, reference, FLAT)

    assert combined.nota_itbi == itbi_only.nota
    assert combined.nota_qpreco < combined.nota_itbi
    assert combined.nota == combined.nota_qpreco


def test_an_agreeing_qpreco_keeps_the_itbi_score() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)
    agreeing = listing(preco_total=500000.0, qpreco=suggestion(preco_sugerido=800000.0))

    itbi_only = compute_opportunity(listing(preco_total=500000.0), pool, reference, FLAT)
    combined = compute_opportunity(agreeing, pool, reference, FLAT)

    assert combined.nota_qpreco >= combined.nota_itbi
    # The second reference confirms the discount; it never inflates the score.
    assert combined.nota == itbi_only.nota


def test_the_qpreco_discount_is_measured_against_the_suggested_price() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    opportunity = compute_opportunity(
        listing(preco_total=500000.0, qpreco=suggestion(preco_sugerido=700000.0)),
        pool,
        reference,
        FLAT,
    )

    assert opportunity.qpreco_estimado == 700000.0
    assert opportunity.qpreco_desconto_pct == pytest.approx(0.2857, abs=0.0001)


def test_a_wide_qpreco_band_weighs_less_than_a_narrow_one() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)
    narrow = suggestion(
        preco_sugerido=700000.0, limite_inferior=680000.0, limite_superior=720000.0
    )
    wide = suggestion(
        preco_sugerido=700000.0, limite_inferior=350000.0, limite_superior=1050000.0
    )

    firm = compute_opportunity(listing(preco_total=500000.0, qpreco=narrow), pool, reference, FLAT)
    vague = compute_opportunity(listing(preco_total=500000.0, qpreco=wide), pool, reference, FLAT)

    # Same suggested price, same asking price: only QuintoAndar's own
    # uncertainty about the estimate differs.
    assert firm.qpreco_desconto_pct == vague.qpreco_desconto_pct
    assert firm.nota_qpreco > vague.nota_qpreco


def test_a_qpreco_without_a_band_is_treated_as_an_ordinary_spread() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)
    bandless = suggestion(preco_sugerido=700000.0, limite_inferior=None, limite_superior=None)

    opportunity = compute_opportunity(
        listing(preco_total=500000.0, qpreco=bandless), pool, reference, FLAT
    )

    assert opportunity.nota_qpreco is not None
    assert opportunity.qpreco_estimado == 700000.0


def test_a_qpreco_of_zero_is_ignored() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    opportunity = compute_opportunity(
        listing(preco_total=500000.0, qpreco=suggestion(preco_sugerido=0.0)),
        pool,
        reference,
        FLAT,
    )

    assert opportunity.qpreco_estimado is None
    assert opportunity.nota == opportunity.nota_itbi


def test_the_qpreco_appears_in_the_reasons() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    opportunity = compute_opportunity(
        listing(preco_total=500000.0, qpreco=suggestion()),
        pool,
        reference,
        FLAT,
    )

    reasons = "\n".join(opportunity.motivos)
    assert "QuintoAndar" in reasons
    assert "700.000,00" in reasons


def test_the_fingerprint_ignores_the_qpreco() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    without = compute_opportunity(listing(preco_total=500000.0), pool, reference, FLAT)
    with_qpreco = compute_opportunity(
        listing(preco_total=500000.0, qpreco=suggestion()), pool, reference, FLAT
    )

    # A moving QuintoAndar estimate must not resend an alert that already went out.
    assert with_qpreco.fingerprint == without.fingerprint


# --- conversão de área: cartório mede diferente do anúncio ---------------------


def test_the_itbi_window_is_centred_on_the_converted_area() -> None:
    reference = date(2026, 6, 30)
    # O ITBI do mesmo apartamento de 90 m² úteis é lançado com área construída
    # em torno de 144 m² (90 x AREA_MATCH_FACTOR).
    cartorio = sales(20, declared_value=1440000.0, built_area_acquired=144.0)

    escolhida = select_reference(listing(area_util_m2=90.0), cartorio, reference)

    assert escolhida is not None
    assert escolhida.tipo_referencia == "endereco_exato"
    assert escolhida.amostra_count == 20


def test_itbi_rows_matching_the_raw_area_are_no_longer_comparable() -> None:
    reference = date(2026, 6, 30)
    # 90 m² de área construída é um apartamento bem menor que o anunciado como
    # 90 m² úteis: fora da janela, ainda que o número coincida.
    homonimos = sales(20, declared_value=900000.0, built_area_acquired=90.0)

    escolhida = select_reference(listing(area_util_m2=90.0), homonimos, reference)

    # Sobra apenas o bairro amplo, que não filtra por área.
    assert escolhida.tipo_referencia == "bairro_amplo"


def test_the_estimate_still_multiplies_the_advertised_area() -> None:
    reference = date(2026, 6, 30)
    # R$ 10.000 por m² construído, 20 vendas no endereço.
    cartorio = sales(20, declared_value=1440000.0, built_area_acquired=144.0)

    opportunity = compute_opportunity(
        listing(area_util_m2=90.0, preco_total=500000.0), cartorio, reference, FLAT
    )

    # A conversão serve para escolher os comparáveis; o preço continua sendo
    # R$/m² da referência vezes a área que o anúncio publica.
    assert opportunity.preco_estimado == pytest.approx(10000.0 * 90.0)


def test_the_reported_area_window_is_in_itbi_terms() -> None:
    reference = date(2026, 6, 30)
    cartorio = sales(20, declared_value=1440000.0, built_area_acquired=144.0)

    escolhida = select_reference(listing(area_util_m2=90.0), cartorio, reference)

    # A faixa exibida descreve os ITBIs comparados, não o anúncio.
    assert escolhida.area_minima == pytest.approx(144.0 * (1 - AREA_TOLERANCE), abs=0.01)
    assert escolhida.area_maxima == pytest.approx(144.0 * (1 + AREA_TOLERANCE), abs=0.01)


# --- pisos calibrados por validação cruzada -----------------------------------


def test_two_sales_at_the_same_address_earn_the_exact_tier() -> None:
    reference = date(2026, 6, 30)

    # Validação cruzada em 8.148 quitações escondidas de BH: baixar o piso de 3
    # para 2 leva 763 previsões a mais para o tier de endereço exato e derruba o
    # erro mediano global de 13,0% para 12,6%. O par sozinho erra mais que uma
    # amostra profunda, mas erra bem menos que a rua que o substituía.
    escolhida = select_reference(listing(), sales(2), reference)

    assert escolhida.tipo_referencia == "endereco_exato"
    assert escolhida.amostra_count == 2


def test_five_sales_on_the_street_earn_the_street_tier() -> None:
    reference = date(2026, 6, 30)
    rua = [sale(street_number=str(200 + i)) for i in range(5)]
    # Mais 20 no bairro, para que o tier de bairro seja alcançável e a escolha
    # do tier de rua seja de fato uma escolha.
    bairro = [sale(street="Rua Outra", street_number=str(i)) for i in range(20)]

    escolhida = select_reference(listing(numero="999"), rua + bairro, reference)

    # A rua erra 18% contra 20% do bairro na validação cruzada, e o piso de 15
    # jogava fora dois terços dos casos em que ela estava disponível.
    assert escolhida.tipo_referencia == "rua"
    assert escolhida.amostra_count == 5


# --- a nota mede o desconto contra o erro medido da referência ----------------


def test_the_same_discount_scores_higher_on_a_tighter_tier() -> None:
    reference = date(2026, 6, 30)
    # Mesmo desconto, mesma dispersão, mesma profundidade: só muda o escopo de
    # onde a referência veio. O endereço exato erra 9,5% onde o bairro erra
    # 19,3% na validação cruzada, e a nota tem que refletir isso.
    exato = score(
        desconto_pct=0.30, dispersao_relativa=0.20,
        tipo_referencia="endereco_exato", preco_anunciado=700000.0,
        preco_estimado=1000000.0,
    )
    bairro = score(
        desconto_pct=0.30, dispersao_relativa=0.20,
        tipo_referencia="bairro_area", preco_anunciado=700000.0,
        preco_estimado=1000000.0,
    )

    assert exato > bairro


def test_sample_depth_alone_no_longer_moves_the_score() -> None:
    reference = date(2026, 6, 30)
    # Cinco vendas e cinquenta, mesmo tier e mesma dispersão: a validação
    # cruzada não vê diferença de erro, então a nota não pode inventar uma.
    rasa = sales(5, declared_value=1280000.0, built_area_acquired=128.0)
    funda = sales(50, declared_value=1280000.0, built_area_acquired=128.0)

    a = compute_opportunity(listing(preco_total=500000.0), rasa, reference, FLAT)
    b = compute_opportunity(listing(preco_total=500000.0), funda, reference, FLAT)

    assert a.amostra_count == 5 and b.amostra_count == 50
    assert a.nota == b.nota


def test_a_dispersed_sample_still_scores_below_a_tight_one() -> None:
    reference = date(2026, 6, 30)

    firme = score(
        desconto_pct=0.30, dispersao_relativa=0.10,
        tipo_referencia="endereco_exato", preco_anunciado=700000.0,
        preco_estimado=1000000.0,
    )
    vaga = score(
        desconto_pct=0.30, dispersao_relativa=0.40,
        tipo_referencia="endereco_exato", preco_anunciado=700000.0,
        preco_estimado=1000000.0,
    )

    assert firme > vaga


def test_expected_error_follows_the_measured_table() -> None:
    # Medido em 8.143 previsões escondidas de Belo Horizonte.
    assert expected_error("endereco_exato", 0.10) < expected_error("endereco_exato", 0.40)
    assert expected_error("endereco_exato", 0.20) < expected_error("rua", 0.20)
    assert expected_error("rua", 0.20) < expected_error("bairro_area", 0.20)
    assert expected_error("bairro_area", 0.20) < expected_error("bairro_amplo", 0.20)


# --- a referência mais precisa disponível define o preço esperado -------------


def test_the_qpreco_becomes_the_expected_price_when_it_exists() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    opportunity = compute_opportunity(
        listing(preco_total=500000.0, qpreco=suggestion(preco_sugerido=700000.0)),
        pool, reference, FLAT,
    )

    # O ITBI erra 22% ao prever preço de anúncio; o qpreço avalia a unidade e
    # publica uma faixa de ~5%. Onde ele existe, é ele que responde "quanto vale".
    assert opportunity.referencia_primaria == "qpreco"
    assert opportunity.preco_estimado == 700000.0
    assert opportunity.desconto_pct == pytest.approx(0.2857, abs=0.0001)


def test_the_itbi_reading_is_kept_alongside() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    opportunity = compute_opportunity(
        listing(preco_total=500000.0, qpreco=suggestion(preco_sugerido=700000.0)),
        pool, reference, FLAT,
    )

    # A leitura de ITBI não some: ela é a checagem, e é o que permite dizer
    # depois qual das duas acertou.
    assert opportunity.preco_estimado_itbi == pytest.approx(800000.0)
    assert opportunity.desconto_itbi_pct == pytest.approx(0.375)


def test_without_a_qpreco_the_itbi_answers() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    opportunity = compute_opportunity(listing(preco_total=500000.0), pool, reference, FLAT)

    assert opportunity.referencia_primaria == "itbi"
    assert opportunity.preco_estimado == opportunity.preco_estimado_itbi


def test_the_discount_floor_scales_with_the_reference_error() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    # 20% abaixo de um qpreço de faixa estreita é quatro vezes o erro esperado
    # daquela referência — nota cheia. O mesmo desconto contra o ITBI, que erra
    # 22% ao prever preço pedido, fica dentro do ruído.
    contra_qpreco = compute_opportunity(
        listing(preco_total=560000.0, qpreco=suggestion(
            preco_sugerido=700000.0, limite_inferior=680000.0, limite_superior=720000.0)),
        pool, reference, FLAT,
    )
    # Referência de rua com dispersão real: é a que erra 22% na validação
    # cruzada, e a que responde pela maioria dos anúncios da base.
    rua = [
        sale(street_number=str(200 + i), declared_value=1280000.0 + offset,
             built_area_acquired=128.0)
        for i, offset in enumerate(range(-600000, 600000, 60000))
    ]
    contra_itbi = compute_opportunity(
        listing(numero="999", preco_total=640000.0), rua, reference, FLAT
    )

    assert contra_qpreco.desconto_pct == pytest.approx(0.20, abs=0.001)
    assert is_alert_eligible(contra_qpreco) is True
    # A mediana da rua dispersa cai em 781.250, então o mesmo pedido de 640.000
    # vale 18% de desconto — praticamente o mesmo número do outro lado.
    assert contra_itbi.desconto_pct == pytest.approx(0.18, abs=0.01)
    assert contra_itbi.tipo_referencia == "rua"
    assert is_alert_eligible(contra_itbi) is False


def test_the_sharper_reference_decides_and_the_other_only_vetoes_contradiction() -> None:
    reference = date(2026, 6, 30)
    # Rua dispersa: a referência que erra 22% e responde pela maioria da base.
    rua = [
        sale(street_number=str(200 + i), declared_value=1280000.0 + offset,
             built_area_acquired=128.0)
        for i, offset in enumerate(range(-600000, 600000, 60000))
    ]
    estreito = suggestion(
        preco_sugerido=700000.0, limite_inferior=680000.0, limite_superior=720000.0
    )

    concorda = compute_opportunity(
        listing(numero="999", preco_total=520000.0, qpreco=estreito), rua, reference, FLAT
    )

    # O ITBI vê o mesmo desconto que o qpreço, só que com régua grossa: nota
    # baixa por dividir por 20% de erro. Deixar isso vetar seria devolver o
    # ruído dele à decisão.
    assert concorda.nota_qpreco > concorda.nota_itbi
    assert concorda.nota == concorda.nota_qpreco


def test_an_itbi_that_calls_the_listing_expensive_still_vetoes() -> None:
    reference = date(2026, 6, 30)
    rua = [
        sale(street_number=str(200 + i), declared_value=500000.0 + offset,
             built_area_acquired=128.0)
        for i, offset in enumerate(range(-100000, 100000, 10000))
    ]
    estreito = suggestion(
        preco_sugerido=900000.0, limite_inferior=880000.0, limite_superior=920000.0
    )

    contradiz = compute_opportunity(
        listing(numero="999", preco_total=700000.0, qpreco=estreito), rua, reference, FLAT
    )

    # Aqui o ITBI não é morno: ele diz que o anúncio pede acima do esperado, e
    # por margem maior que o próprio erro dele. Isso é contradição, e derruba.
    assert contradiz.desconto_itbi_pct < 0
    assert contradiz.nota < contradiz.nota_qpreco


# --- régua emprestada dos vizinhos --------------------------------------------


def vizinhos(preco_m2: float = 10000.0, dispersao: float = 0.10, amostra: int = 6):
    return NeighbourEstimate(preco_m2=preco_m2, dispersao=dispersao, amostra=amostra)


def test_neighbours_answer_when_the_listing_has_no_qpreco_of_its_own() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    # Loft e VivaReal nunca terão qpreço próprio — o endpoint resolve por id do
    # QuintoAndar. Mas metade deles divide rua e faixa de área com um anúncio
    # que tem: emprestar a mediana desses vizinhos erra 6,7%, contra 22,2% da
    # escada de ITBI.
    opportunity = compute_opportunity(
        listing(preco_total=500000.0, qpreco_vizinhos=vizinhos(preco_m2=10000.0)),
        pool, reference, FLAT,
    )

    assert opportunity.referencia_primaria == "qpreco_vizinho"
    assert opportunity.preco_estimado == pytest.approx(800000.0)


def test_the_listings_own_qpreco_beats_the_neighbours() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    opportunity = compute_opportunity(
        listing(preco_total=500000.0, qpreco=suggestion(preco_sugerido=700000.0),
                qpreco_vizinhos=vizinhos()),
        pool, reference, FLAT,
    )

    # Avaliação da própria unidade sempre vale mais que a dos vizinhos dela.
    assert opportunity.referencia_primaria == "qpreco"
    assert opportunity.preco_estimado == 700000.0


def test_dispersed_neighbours_are_worth_less_than_agreeing_ones() -> None:
    reference = date(2026, 6, 30)
    pool = sales(20, declared_value=1280000.0, built_area_acquired=128.0)

    firme = compute_opportunity(
        listing(preco_total=600000.0, qpreco_vizinhos=vizinhos(dispersao=0.10)),
        pool, reference, FLAT,
    )
    vago = compute_opportunity(
        listing(preco_total=600000.0, qpreco_vizinhos=vizinhos(dispersao=0.40)),
        pool, reference, FLAT,
    )

    # Vizinhos que concordam erram 3,5%; dispersos erram 13,2%.
    assert firme.desconto_pct == vago.desconto_pct
    assert firme.nota > vago.nota


# --- prédio homogêneo dispensa a janela de área --------------------------------


def _venda(area: float, valor: float = 1_000_000.0) -> Sale:
    return Sale(
        neighborhood="SAVASSI",
        street="Rua Sao Joao",
        street_number="10",
        settlement_date=date(2026, 6, 30),
        declared_value=valor,
        built_area_acquired=area,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
    )


def _anuncio(**extra) -> ListingInput:
    base = dict(
        source="loft",
        listing_id="x",
        tipo_imovel="APARTAMENTO",
        area_util_m2=80.0,
        preco_total=800_000.0,
        bairro="Savassi",
        rua="Rua Sao Joao",
        numero="10",
    )
    base.update(extra)
    return ListingInput(**base)


def test_predio_homogeneo_aceita_venda_fora_da_janela_de_area():
    # 80 m² anunciados viram 128 m² esperados; 200 m² está muito fora da
    # janela de ±30%, mas o cadastro diz que este prédio é uniforme.
    vendas = [_venda(200.0), _venda(200.0)]
    referencia = select_reference(
        _anuncio(predio_dispersao_area=0.05), vendas, date(2026, 6, 30)
    )
    assert referencia is not None
    assert referencia.tipo_referencia == "endereco_exato"
    assert referencia.amostra_count == 2
    # Sem janela, não há faixa de área a declarar.
    assert referencia.area_minima is None and referencia.area_maxima is None


def test_predio_heterogeneo_mantem_a_janela_de_area():
    vendas = [_venda(200.0), _venda(200.0)]
    referencia = select_reference(
        _anuncio(predio_dispersao_area=0.60), vendas, date(2026, 6, 30)
    )
    # Sem amostra no endereço dentro da janela, cai da escada.
    assert referencia is None or referencia.tipo_referencia != "endereco_exato"


def test_predio_desconhecido_mantem_a_janela_de_area():
    vendas = [_venda(200.0), _venda(200.0)]
    referencia = select_reference(_anuncio(), vendas, date(2026, 6, 30))
    assert referencia is None or referencia.tipo_referencia != "endereco_exato"


def test_o_limiar_de_homogeneidade_e_a_propria_tolerancia_da_janela():
    assert HOMOGENEOUS_BUILDING_DISPERSION == AREA_TOLERANCE


def test_a_janela_some_exatamente_no_limiar():
    vendas = [_venda(200.0), _venda(200.0)]
    no_limite = select_reference(
        _anuncio(predio_dispersao_area=HOMOGENEOUS_BUILDING_DISPERSION), vendas, date(2026, 6, 30)
    )
    assert no_limite is not None and no_limite.tipo_referencia == "endereco_exato"


# --- faixas de leitura da nota ------------------------------------------------


def test_cada_corte_de_faixa_e_um_multiplo_do_erro_da_referencia():
    """As faixas não são números escolhidos a dedo: elas saem da própria nota.

    A nota é `100 x força x plausibilidade`, com força limitada a 1 e igual a
    `desconto / (SCORE_FULL_SIGNAL x erro)`. Então uma nota de corte N
    corresponde a um desconto de `N/100 x SCORE_FULL_SIGNAL` vezes o erro
    típico da referência que respondeu.
    """
    erro = 0.10
    for corte, _, _ in SCORE_BANDS:
        if corte == 0:
            continue
        desconto = (corte / 100) * SCORE_FULL_SIGNAL * erro
        nota = score(
            desconto_pct=desconto,
            dispersao_relativa=0.20,
            tipo_referencia="qpreco",
            preco_anunciado=100.0,
            preco_estimado=100.0,
        )
        assert nota == corte


def test_a_faixa_de_cada_nota():
    assert score_band(100) == "forte"
    assert score_band(80) == "forte"
    assert score_band(79) == "oferta"
    assert score_band(60) == "oferta"
    assert score_band(59) == "monitorar"
    assert score_band(40) == "monitorar"
    assert score_band(39) == "ruido"
    assert score_band(20) == "ruido"
    assert score_band(19) == "sem_sinal"
    assert score_band(0) == "sem_sinal"


def test_sem_nota_nao_ha_faixa():
    assert score_band(None) is None


def test_o_corte_de_alerta_cai_na_faixa_mais_forte():
    # Quem dispara e-mail continua sendo MIN_SCORE; a faixa é só como se lê.
    assert score_band(MIN_SCORE) == "forte"


def test_toda_faixa_tem_uma_frase_que_a_explica():
    for _, chave, _ in SCORE_BANDS:
        assert score_band_label(chave)
    assert score_band_label("inexistente") is None
    assert score_band_label(None) is None
