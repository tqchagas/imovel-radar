"""City-scoped insight definitions shared by the API and SEO pages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InsightMetrics:
    transaction_count: int
    appreciation_count: int
    flip_count: int
    priciest_sale_count: int
    riser_count: int
    building_count: int


@dataclass(frozen=True, slots=True)
class InsightSummary:
    slug: str
    title: str
    description: str
    count: int
    url: str


@dataclass(frozen=True, slots=True)
class _InsightDefinition:
    slug: str
    title: str
    description: str
    metric: str
    minimum: int


_DEFINITIONS = (
    _InsightDefinition(
        "maiores-valorizacoes",
        "Maiores valorizações",
        "As unidades que mais subiram de valor entre duas vendas.",
        "appreciation_count",
        3,
    ),
    _InsightDefinition(
        "revendas-mais-rapidas",
        "Revendas mais rápidas",
        "As unidades que trocaram de dono no menor intervalo.",
        "flip_count",
        3,
    ),
    _InsightDefinition(
        "maiores-vendas",
        "Maiores vendas",
        "Os maiores valores declarados em quitações de ITBI.",
        "priciest_sale_count",
        1,
    ),
    _InsightDefinition(
        "bairros-em-alta",
        "Bairros em alta",
        "Os bairros com maior alta de R$/m² na janela recente.",
        "riser_count",
        1,
    ),
    _InsightDefinition(
        "ruas-mais-movimentadas",
        "Ruas mais movimentadas",
        "Os endereços com mais quitações na base.",
        "building_count",
        1,
    ),
)


def city_is_enabled(city_slug: str, enabled_cities: set[str]) -> bool:
    return city_slug in enabled_cities


def available_insights(city_slug: str, metrics: InsightMetrics) -> list[InsightSummary]:
    """Return only pages with enough evidence to deserve publication."""
    summaries = []
    for definition in _DEFINITIONS:
        count = getattr(metrics, definition.metric)
        if count < definition.minimum:
            continue
        summaries.append(
            InsightSummary(
                slug=definition.slug,
                title=definition.title,
                description=definition.description,
                count=count,
                url=f"/curiosidades/{city_slug}/{definition.slug}/",
            )
        )
    return summaries
