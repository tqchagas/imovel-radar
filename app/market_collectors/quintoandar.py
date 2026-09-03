from __future__ import annotations

import os
from typing import Any

from app.core.http_client import request
from app.market_collectors.normalize import canonical_scope_key, is_portal_url, listing, query_type, safe_float, safe_int, slug
from app.market_collectors.types import CollectionResult, MarketQuery

SOURCE = "quintoandar"
API_URL = "https://apigw.prod.quintoandar.com.br/house-listing-search/v3/search/list"

# The gateway rejects (400) any request whose pageSize + offset exceeds 1000,
# and any pageSize above 500. A scope with more listings than RESULT_CAP can
# only be collected by splitting the query into narrower ones.
PAGE_SIZE = 500
RESULT_CAP = 1000

# Without an explicit field list the gateway answers with `id` alone, so every
# row would be dropped for having no price.
FIELDS = (
    "id",
    "salePrice",
    "totalCost",
    "iptuPlusCondominium",
    "area",
    "address",
    "regionName",
    "city",
    "neighbourhood",
    "type",
    "forSale",
    # Coordenada do imóvel. O gateway só devolve o que a lista pede, e sem ela
    # esta fonte não alcançava o cadastro imobiliário — e portanto nem o tier
    # de endereço, nem o mapa.
    "location",
    "bedrooms",
    "bathrooms",
    "suites",
    "parkingSpaces",
    "isPrimaryMarket",
)

HOUSE_TYPE = {"CASA": "Casa", "APARTAMENTO": "Apartamento"}


def _rows(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload_structure")
    hits = payload.get("hits")
    if not isinstance(hits, dict):
        raise ValueError("invalid_payload_structure")
    rows = hits.get("hits")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid_payload_structure")
    extracted = [row.get("_source", row) for row in rows]
    if any(not isinstance(row, dict) for row in extracted):
        raise ValueError("invalid_payload_structure")
    return extracted, _total(hits.get("total"))


def _total(value: Any) -> int | None:
    if isinstance(value, dict):
        if str(value.get("relation", "")).lower() == "gte":
            return None
        return safe_int(value.get("value"))
    return safe_int(value)


def _parse(row: dict[str, Any], query: MarketQuery):
    identifier = str(row.get("id") or "").strip()
    price = safe_float(row.get("salePrice"), positive=True)
    if not identifier or price is None:
        return None
    url = f"https://www.quintoandar.com.br/imovel/{identifier}/comprar"
    if not is_portal_url(SOURCE, url):
        return None
    # `address` carries the street name only - the portal never exposes the
    # street number on search results. O número vem depois, do cadastro
    # imobiliário da prefeitura, pelo lote mais próximo da coordenada.
    street = row.get("address")
    location = row.get("location") if isinstance(row.get("location"), dict) else {}
    lat = safe_float(location.get("lat"), allow_negative=True)
    lon = safe_float(location.get("lon"), allow_negative=True)
    parsed = listing(
        SOURCE,
        query,
        row,
        listing_id=identifier,
        url=url,
        cidade=row.get("city"),
        bairro=row.get("neighbourhood") or row.get("regionName"),
        rua=street if isinstance(street, str) and street.strip() else None,
        numero=None,
        tipo_imovel=row.get("type"),
        quartos=row.get("bedrooms"),
        area_util_m2=row.get("area"),
        preco_total=price,
        bathrooms=row.get("bathrooms"),
        suites=row.get("suites"),
        parking_spaces=row.get("parkingSpaces"),
        lat=lat,
        lon=lon,
        coordinate_source="QUINTOANDAR_LOCATION" if lat is not None else None,
    )
    return parsed if parsed.tipo_imovel else None


def _house_specs(query: MarketQuery, requested_type: str | None) -> dict[str, Any]:
    specs: dict[str, Any] = {
        "area": {"range": {}},
        "houseTypes": [HOUSE_TYPE[requested_type]] if requested_type else [],
        "amenities": [],
        "installations": [],
        "bathrooms": {"range": {}},
        "bedrooms": {"range": {}},
        "parkingSpace": {"range": {}},
        "suites": {"range": {}},
    }
    if query.quartos is not None:
        specs["bedrooms"] = {"range": {"min": query.quartos, "max": query.quartos}}
    if query.area_util_m2 is not None:
        specs["area"] = {"range": {"min": query.area_util_m2, "max": query.area_util_m2}}
    return specs


def _payload(query: MarketQuery, requested_type: str | None, page_size: int, offset: int) -> dict[str, Any]:
    location = f"{slug(query.bairro)}-" if query.bairro else ""
    description = f"{location}{slug(query.cidade)}-{query.uf.lower()}-brasil"
    return {
        "slug": description,
        "topics": [],
        "fields": list(FIELDS),
        "sorting": {"criteria": "RELEVANCE", "order": "DESC"},
        "pagination": {"pageSize": page_size, "offset": offset},
        "context": {"listShowing": True, "mapShowing": False, "numPhotos": 0, "isSSR": False},
        "filters": {
            "unknownSlugs": [],
            "enableFlexibleSearch": True,
            "businessContext": "SALE",
            "priceRange": [],
            "availability": "ANY",
            "occupancy": "ANY",
            "partnerIds": [],
            "specialConditions": [],
            "excludedSpecialConditions": [],
            "blocklist": [],
            "selectedHouses": [],
            "categories": [],
            "houseSpecs": _house_specs(query, requested_type),
            "origin": "HYBRID",
        },
        "locationDescriptions": [{"description": description}],
    }


def collect(query: MarketQuery) -> CollectionResult:
    limit = max(1, query.max_pages or 100)
    listings = []
    seen: set[str] = set()
    pages = 0
    page_attempted = False
    total: int | None = None
    scope_key = canonical_scope_key(query, SOURCE)
    try:
        requested_type = query_type(query.tipo_imovel)
        url = os.getenv("QUINTOANDAR_SEARCH_API_URL", API_URL)
        for page in range(1, limit + 1):
            offset = (page - 1) * PAGE_SIZE
            page_size = min(PAGE_SIZE, RESULT_CAP - offset)
            if page_size <= 0:
                # Everything past the gateway cap is unreachable for this scope.
                return CollectionResult(SOURCE, listings, False, True, scope_key, pages, "result_cap_reached", total)
            page_attempted = True
            response = request(
                "POST",
                url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Origin": "https://www.quintoandar.com.br",
                    "User-Agent": "Mozilla/5.0",
                },
                json_body=_payload(query, requested_type, page_size, offset),
                timeout=25,
            )
            if not 200 <= int(response.status_code) < 300:
                raise RuntimeError(f"http_{response.status_code}")
            rows, reported_total = _rows(response.json())
            pages += 1
            if reported_total is not None:
                total = reported_total if total is None else max(total, reported_total)
            for row in rows:
                parsed = _parse(row, query)
                if parsed and parsed.listing_id not in seen:
                    seen.add(parsed.listing_id)
                    listings.append(parsed)
            if not rows or len(rows) < page_size:
                break
            if total is not None and offset + len(rows) >= total:
                break
            if offset + page_size >= RESULT_CAP:
                # More listings exist than the API will paginate through. Report
                # partial so the refresh never deactivates what it could not see.
                return CollectionResult(SOURCE, listings, False, True, scope_key, pages, "result_cap_reached", total)
        else:
            return CollectionResult(SOURCE, listings, False, True, scope_key, pages, "max_pages_reached", total)
        return CollectionResult(SOURCE, listings, True, False, scope_key, pages, total=total)
    except Exception as exc:
        return CollectionResult(SOURCE, listings, False, page_attempted, scope_key, pages, str(exc), total)


collect_quintoandar = collect
