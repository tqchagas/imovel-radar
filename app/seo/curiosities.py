"""Server-rendered curiosity hubs and ranking pages."""

from __future__ import annotations

from app.api.routes.curiosities import get_curiosities
from app.core.config import settings
from app.domain.insights import InsightMetrics, available_insights, city_is_enabled
from app.domain.slugs import neighborhood_path, property_path, slugify, stored_city, street_path
from app.seo.metadata import build_metadata
from app.seo.schema import breadcrumb_json_ld, webpage_json_ld


ENABLED_CITY_SLUGS = {"belo-horizonte"}


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _metrics(board) -> InsightMetrics:
    return InsightMetrics(
        transaction_count=board.transaction_count,
        appreciation_count=len(board.top_appreciation),
        flip_count=len(board.fastest_flips),
        priciest_sale_count=len(board.priciest_sales),
        riser_count=len(board.risers),
        building_count=len(board.top_buildings),
    )


def _unit_row(unit, city_slug: str, value: float | None = None) -> dict[str, str]:
    label = unit.street
    if unit.street_number:
        label += f", {unit.street_number}"
    if unit.complement:
        label += f" — {unit.complement}"
    return {
        "label": label,
        "neighborhood": unit.neighborhood,
        "value": _money(value),
        "url": property_path(city_slug, unit.street, unit.street_number, unit.complement),
    }


def _rows(board, kind: str, city_slug: str) -> list[dict[str, str]]:
    if kind == "maiores-valorizacoes":
        return [
            {
                **_unit_row(item.unit, city_slug, item.to_value),
                "detail": f"{item.total_pct:+.0f}% no período de {item.from_date.year} a {item.to_date.year}",
            }
            for item in board.top_appreciation
        ]
    if kind == "revendas-mais-rapidas":
        return [
            {
                **_unit_row(item.unit, city_slug, item.to_value),
                "detail": f"{item.days} dias entre as quitações",
            }
            for item in board.fastest_flips
        ]
    if kind == "maiores-vendas":
        return [
            {
                **_unit_row(item.unit, city_slug, item.declared_value),
                "detail": f"{item.settlement_date.strftime('%d/%m/%Y')} · {_money(item.price_per_m2)} por m²",
            }
            for item in board.priciest_sales
        ]
    if kind == "bairros-em-alta":
        return [
            {
                "label": item.neighborhood,
                "neighborhood": f"{item.transaction_count} quitações",
                "value": _money(item.median_price_per_m2),
                "detail": f"{item.delta_pct:+.1f}% na janela recente",
                "url": neighborhood_path(city_slug, item.neighborhood),
            }
            for item in board.risers
        ]
    if kind == "ruas-mais-movimentadas":
        return [
            {
                "label": f"{item.street}, {item.street_number}" if item.street_number else item.street,
                "neighborhood": item.neighborhood,
                "value": f"{item.transaction_count} quitações",
                "detail": f"{item.unit_count} unidades distintas",
                "url": street_path(city_slug, item.street),
            }
            for item in board.top_buildings
        ]
    return []


def curiosity_context(db, city_slug: str, kind: str | None = None) -> dict[str, object] | None:
    if not city_is_enabled(city_slug, ENABLED_CITY_SLUGS):
        return None

    city = stored_city(city_slug)
    board = get_curiosities(city=city, months=12, construction_type=None, db=db)
    insights = available_insights(city_slug, _metrics(board))
    selected = next((item for item in insights if item.slug == kind), None) if kind else None
    if kind and selected is None:
        return None

    city_label = city.replace("_", " ").title()
    path = f"/curiosidades/{city_slug}/" if kind is None else f"/curiosidades/{city_slug}/{kind}/"
    title = (
        f"Curiosidades de {city_label} sobre imóveis | ImovelRadar"
        if kind is None
        else f"{selected.title} em {city_label} | ImovelRadar"
    )
    description = (
        f"Descubra padrões, recordes e histórias das {board.transaction_count} quitações de ITBI em {city_label}."
        if kind is None
        else f"Veja {selected.description.lower()} na base de quitações de ITBI de {city_label}."
    )
    return {
        "metadata": build_metadata(title=title, description=description, canonical=path, base_url=settings.public_base_url),
        "json_ld": [
            breadcrumb_json_ld([("Início", "/"), ("Curiosidades", "/curiosidades"), (city_label, path)], settings.public_base_url),
            webpage_json_ld(title, description, settings.public_base_url.rstrip("/") + path),
        ],
        "page_script": None,
        "city": city_label,
        "exploration_url": f"/busca?city={city}",
        "exploration_label": f"Explorar imóveis em {city_label}",
        "transaction_count": board.transaction_count,
        "insights": insights,
        "selected": selected,
        "rows": _rows(board, kind, city_slug) if kind else [],
    }
