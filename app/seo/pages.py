"""Build server-rendered contexts for indexable research pages."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.market_stats import neighborhood_detail
from app.domain.slugs import neighborhood_path, property_path, slugify, street_path, stored_city
from app.domain.street_stats import street_detail
from app.models.transaction import Transaction
from app.schemas.property import PropertyOut
from app.seo.content import neighborhood_intro, property_intro, street_intro
from app.seo.eligibility import neighborhood_quality, property_quality, street_quality
from app.seo.metadata import build_metadata
from app.seo.schema import breadcrumb_json_ld, webpage_json_ld
from app.services.market_data import fetch_window_sales
from app.services.property_data import get_property_from_slugs


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _number(value: float | int | None, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _resolve_name(db: Session, city: str, slug: str, field) -> str | None:
    values = db.scalars(select(field).where(Transaction.city == stored_city(city)).distinct()).all()
    return next((value for value in values if value and slugify(value) == slug), None)


def _base_context(metadata, json_ld: list[dict[str, object]], page_script: str | None = None) -> dict[str, object]:
    return {"metadata": metadata, "json_ld": json_ld, "page_script": page_script}


def neighborhood_context(db: Session, city_slug: str, neighborhood_slug: str, months: int = 12) -> dict[str, object] | None:
    city = stored_city(city_slug)
    neighborhood = _resolve_name(db, city, neighborhood_slug, Transaction.neighborhood)
    if neighborhood is None:
        return None
    reference, sales = fetch_window_sales(db, city, months, neighborhood=neighborhood)
    if reference is None:
        return None
    detail = neighborhood_detail(sales, neighborhood, reference, months)
    valid_area_count = sum(1 for sale in sales if sale.built_area_acquired and sale.built_area_acquired > 0)
    quality = neighborhood_quality(detail.transaction_count, valid_area_count)
    path = neighborhood_path(city_slug, neighborhood)
    title = f"Preço dos imóveis em {neighborhood.title()}: R$/m² e histórico | ImovelRadar"
    description = f"Veja preços declarados em {detail.transaction_count} quitações de ITBI em {neighborhood.title()}, com R$/m², tendência e histórico."
    metadata = build_metadata(title=title, description=description, canonical=path, base_url=settings.public_base_url, indexable=quality.indexable)
    json_ld = [
        breadcrumb_json_ld([("Início", "/"), ("Bairros", "/bairro"), (neighborhood.title(), path)], settings.public_base_url),
        webpage_json_ld(title, description, metadata.canonical),
    ]
    streets = [
        {"name": item.street, "count": item.transaction_count, "url": street_path(city_slug, item.street)}
        for item in detail.top_streets
    ]
    return {
        **_base_context(metadata, json_ld, "bairro.js"),
        "neighborhood": neighborhood.title(),
        "intro": neighborhood_intro(neighborhood, city, detail.transaction_count, detail.median_price_per_m2, detail.delta_pct),
        "methodology": "Fonte: quitações de ITBI publicadas em dados abertos. A mediana reduz o efeito de valores extremos e o período é ancorado na última data disponível.",
        "metrics": {
            "m2": _money(detail.median_price_per_m2),
            "ticket": _money(detail.median_ticket),
            "range": f"P25 {_money(detail.p25_ticket)} · P75 {_money(detail.p75_ticket)}",
            "area": f"{_number(detail.median_area, 0)} m²",
            "liquidity": f"{_number(detail.per_month, 1)}/mês",
            "delta": f"{detail.delta_pct:+.1f}% vs. janela anterior" if detail.delta_pct is not None else "sem comparação",
        },
        "types": [{"label": item.label, "description": item.description, "value": _money(item.median_price_per_m2), "count": item.transaction_count} for item in detail.by_construction_type],
        "streets": streets,
        "quality": quality,
    }


def street_context(db: Session, city_slug: str, street_slug: str, months: int = 12) -> dict[str, object] | None:
    city = stored_city(city_slug)
    street = _resolve_name(db, city, street_slug, Transaction.street)
    if street is None:
        return None
    reference, sales = fetch_window_sales(db, city, months, street=street)
    if reference is None:
        return None
    detail = street_detail(sales, street, reference, months)
    quality = street_quality(detail.transaction_count, detail.property_count)
    neighborhood = next((sale.neighborhood for sale in sales if sale.neighborhood), None)
    path = street_path(city_slug, street)
    title = f"Imóveis na {street.title()}, {city.replace('_', ' ').title()}: preços e histórico"
    description = f"Consulte {detail.transaction_count} quitações de ITBI e o histórico de {detail.property_count} endereços na {street.title()}."
    metadata = build_metadata(title=title, description=description, canonical=path, base_url=settings.public_base_url, indexable=quality.indexable)
    json_ld = [breadcrumb_json_ld([("Início", "/"), ("Bairros", "/bairro"), (street.title(), path)], settings.public_base_url), webpage_json_ld(title, description, metadata.canonical)]
    return {
        **_base_context(metadata, json_ld),
        "street": street.title(),
        "neighborhood": neighborhood.title() if neighborhood else "Bairro",
        "neighborhood_url": neighborhood_path(city_slug, neighborhood) if neighborhood else "/bairro",
        "intro": street_intro(street, city, detail.transaction_count, detail.property_count, detail.median_price_per_m2),
        "metrics": {"m2": _money(detail.median_price_per_m2), "ticket": _money(detail.median_ticket), "properties": detail.property_count, "transactions": detail.transaction_count},
        "addresses": [{"number": item.street_number, "count": item.transaction_count, "m2": _money(item.median_price_per_m2), "last_date": _date(item.last_settlement_date), "url": property_path(city_slug, street, item.street_number)} for item in detail.top_addresses],
        "quality": quality,
    }


def property_context(db: Session, city_slug: str, street_slug: str, street_number: str, complement_slug: str | None) -> dict[str, object] | None:
    property_data = get_property_from_slugs(db, city_slug, street_slug, street_number, complement_slug)
    if property_data is None:
        return None
    quality = property_quality(property_data.summary.transaction_count)
    address = f"{property_data.street.title()}, {property_data.street_number or 's/n'}"
    if property_data.complement:
        address += f" — {property_data.complement}"
    path = property_path(city_slug, property_data.street, property_data.street_number, property_data.complement)
    title = f"Histórico do imóvel na {address}, {property_data.city.replace('_', ' ').title()} | ImovelRadar"
    description = f"Veja o histórico de {property_data.summary.transaction_count} quitações de ITBI, valores declarados e R$/m² para {address}."
    metadata = build_metadata(title=title, description=description, canonical=path, base_url=settings.public_base_url, indexable=quality.indexable)
    street_url = street_path(city_slug, property_data.street)
    json_ld = [breadcrumb_json_ld([("Início", "/"), ("Rua", street_url), (address, path)], settings.public_base_url), webpage_json_ld(title, description, metadata.canonical)]
    summary = property_data.summary
    return {
        **_base_context(metadata, json_ld, "property.js"),
        "address": address,
        "city": property_data.city.replace("_", " ").title(),
        "street": property_data.street.title(),
        "street_url": street_url,
        "intro": property_intro(property_data.street, property_data.street_number, property_data.complement, summary.transaction_count, summary.year_from, summary.year_to),
        "summary": {"last_sale": _money(summary.last_sale_value), "last_date": _date(summary.last_sale_date), "appreciation": f"{summary.appreciation_pct:+.1f}%" if summary.appreciation_pct is not None else "—", "m2": _money(summary.last_price_per_m2), "count": summary.transaction_count, "years": f"{summary.year_from}–{summary.year_to}" if summary.year_from and summary.year_to else ""},
        "timeline": [{"date": _date(point.settlement_date), "value": _money(point.declared_value), "markers": point.markers} for point in property_data.timeline],
        "history": [
            {
                "date": _date(item.settlement_date),
                "area": f"{_number(item.built_area_acquired, 0)} m²",
                "value": _money(item.declared_value),
                "base": _money(item.calc_base_value),
                "m2": _money(
                    item.declared_value / item.built_area_acquired
                    if item.built_area_acquired and item.built_area_acquired > 0
                    else None
                ),
            }
            for item in property_data.transactions
        ],
        "quality": quality,
    }
