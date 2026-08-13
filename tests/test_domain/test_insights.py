from app.domain.insights import InsightMetrics, available_insights, city_is_enabled


def test_available_insights_only_exposes_rankings_with_enough_evidence():
    metrics = InsightMetrics(
        transaction_count=240,
        appreciation_count=8,
        flip_count=2,
        priciest_sale_count=10,
        riser_count=6,
        building_count=12,
    )

    insights = available_insights("belo-horizonte", metrics)

    assert [item.slug for item in insights] == [
        "maiores-valorizacoes",
        "maiores-vendas",
        "bairros-em-alta",
        "ruas-mais-movimentadas",
    ]
    assert all(item.url.startswith("/curiosidades/belo-horizonte/") for item in insights)


def test_city_enablement_is_configurable_instead_of_hardcoded_in_the_domain():
    assert city_is_enabled("belo-horizonte", {"belo-horizonte"}) is True
    assert city_is_enabled("sao-paulo", {"belo-horizonte"}) is False
