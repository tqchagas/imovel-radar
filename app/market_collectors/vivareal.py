from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, parse_qsl, urlsplit, urlunparse, urlunsplit

from app.core.http_client import request
from app.market_collectors.normalize import canonical_scope_key, is_portal_url, listing, query_type, safe_float, safe_int
from app.market_collectors.types import CollectionResult, MarketQuery

SOURCE = "vivareal"
API_URL = "https://glue-api.vivareal.com/v4/listings"

# `size` above 30 answers 400, and any `from` at or past 1500 answers 404.
PAGE_SIZE = 30
RESULT_CAP = 1500

UNIT_TYPE = {"CASA": "HOME", "APARTAMENTO": "APARTMENT"}

# `addressState` only matches on the spelled-out state name; the acronym
# silently returns zero results instead of an error.
STATE_NAME = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia",
    "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}


def _rows(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload_structure")
    search = payload.get("search")
    result = search.get("result") if isinstance(search, dict) else None
    rows = result.get("listings") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise ValueError("invalid_payload_structure")
    meta = result if isinstance(result, dict) else {}
    total = _first_total(_total(meta.get("totalCount")), _total(meta.get("total")), _total(payload.get("totalCount")), _total(payload.get("total")))
    if total is None and isinstance(search, dict):
        total = _first_total(_total(search.get("totalCount")), _total(search.get("total")))
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid_payload_structure")
    normalized_rows = []
    for row in rows:
        item = row.get("listing", row)
        if not isinstance(item, dict):
            raise ValueError("invalid_payload_structure")
        # `link` is a sibling of `listing` in the envelope, and it is the only
        # place the real listing URL appears.
        if isinstance(row.get("link"), dict) and "link" not in item:
            item = {**item, "link": row["link"]}
        normalized_rows.append(item)
    return normalized_rows, total


def _total(value: Any) -> int | None:
    if isinstance(value, dict):
        if str(value.get("relation", "")).lower() == "gte":
            return None
        if "value" in value:
            return safe_int(value["value"])
        for key in ("total", "totalCount", "totalResults", "totalItems"):
            found = _total(value.get(key))
            if found is not None:
                return found
        return None
    return safe_int(value)


def _first_total(*values: int | None) -> int | None:
    return next((value for value in values if value is not None), None)


def _sale_prices(row: dict[str, Any]) -> list[float]:
    pricing = row.get("pricingInfos")
    if isinstance(pricing, dict):
        pricing = [pricing]
    if not isinstance(pricing, list):
        return []
    prices = []
    for info in pricing:
        if isinstance(info, dict) and str(info.get("businessType", "")).upper() == "SALE":
            price = safe_float(info.get("price") or info.get("salePrice"), positive=True)
            if price is not None:
                prices.append(price)
    return prices


def _single(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if len(value) == 1 else None
    return value


def _parse(row: dict[str, Any], query: MarketQuery):
    identifier = str(row.get("id") or row.get("externalId") or row.get("legacyId") or "").strip()
    prices = _sale_prices(row)
    areas = row.get("usableAreas") or []
    # A DEVELOPMENT advertises a whole building: several units share one row and
    # the areas and prices come back as ranges. Pairing the smallest area with
    # the lowest price would invent an R$/m2 no real unit is sold at.
    if not identifier or len(prices) != 1 or (isinstance(areas, list) and len(areas) > 1):
        return None
    if str(row.get("listingType", "")).upper() == "DEVELOPMENT":
        return None
    price = prices[0]
    link = row.get("link")
    raw_url = link.get("href") if isinstance(link, dict) else link
    url = urljoin("https://www.vivareal.com.br", str(raw_url or f"/imovel/id-{identifier}/"))
    if not is_portal_url(SOURCE, url):
        return None
    url_parts = urlsplit(url)
    url = urlunsplit((url_parts.scheme, url_parts.netloc, url_parts.path, "", ""))
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    point = address.get("point") if isinstance(address.get("point"), dict) else {}
    approximate = point.get("lat") is None and point.get("approximateLat") is not None
    parsed = listing(
        SOURCE,
        query,
        row,
        listing_id=identifier,
        url=url,
        cidade=address.get("city"),
        bairro=address.get("neighborhood") or query.bairro,
        rua=address.get("street") or address.get("streetName"),
        numero=address.get("streetNumber") or None,
        tipo_imovel=(row.get("unitTypes") or [row.get("propertyType")])[0],
        quartos=_single(row.get("bedrooms")),
        bathrooms=_single(row.get("bathrooms")),
        suites=_single(row.get("suites")),
        parking_spaces=_single(row.get("parkingSpaces")),
        area_util_m2=areas[0] if isinstance(areas, list) and areas else None,
        preco_total=price,
        lat=point.get("lat") or point.get("approximateLat"),
        lon=point.get("lon") or point.get("approximateLon"),
        coordinate_source="APPROXIMATE" if approximate else "VIVAREAL_POINT" if point.get("lat") is not None else None,
    )
    return parsed if parsed.tipo_imovel else None


def _params(query: MarketQuery, requested_type: str | None, page: int, offset: int) -> dict[str, str]:
    # `categoryPage` is the one non-obvious requirement: without it the gateway
    # answers 500 no matter how complete the rest of the query is.
    params: dict[str, str] = {
        "categoryPage": "RESULT",
        "business": "SALE",
        "portal": "VIVAREAL",
        "usageTypes": "RESIDENTIAL",
        "page": str(page),
        "size": str(PAGE_SIZE),
        "from": str(offset),
        "addressCity": query.cidade,
        "addressState": STATE_NAME.get(query.uf.strip().upper(), query.uf),
    }
    if query.bairro:
        params["addressNeighborhood"] = query.bairro
        params["addressType"] = "neighborhood"
    else:
        params["addressType"] = "city"
    if requested_type:
        params["unitTypes"] = UNIT_TYPE[requested_type]
        params["unitTypesV3"] = UNIT_TYPE[requested_type]
    if query.quartos is not None:
        params["bedrooms"] = str(query.quartos)
    if query.area_util_m2 is not None:
        params["usableAreas"] = str(query.area_util_m2)
    return params


def collect(query: MarketQuery) -> CollectionResult:
    limit = max(1, query.max_pages or 100)
    output = []
    seen: set[str] = set()
    pages = 0
    page_attempted = False
    total: int | None = None
    scope_key = canonical_scope_key(query, SOURCE)
    try:
        requested_type = query_type(query.tipo_imovel)
        base = os.getenv("VIVAREAL_API_URL", API_URL)
        parsed_base = urlparse(base)
        for page in range(1, limit + 1):
            offset = (page - 1) * PAGE_SIZE
            if offset >= RESULT_CAP:
                return CollectionResult(SOURCE, output, False, True, scope_key, pages, "result_cap_reached", total)
            params = dict(parse_qsl(parsed_base.query, keep_blank_values=True))
            params.update(_params(query, requested_type, page, offset))
            url = urlunparse(parsed_base._replace(query=urlencode(params)))
            page_attempted = True
            response = request(
                "GET",
                url,
                # Header names must stay Title-Cased: Cloudflare answers 403 to
                # the all-lowercase form regardless of the values sent.
                headers={
                    "Accept": "application/json",
                    "Origin": "https://www.vivareal.com.br",
                    "Referer": "https://www.vivareal.com.br/",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    # The leading-dot form (".vivareal.com.br") is also a 403.
                    "X-Domain": "www.vivareal.com.br",
                },
                timeout=25,
            )
            if not 200 <= int(response.status_code) < 300:
                raise RuntimeError(f"http_{response.status_code}")
            rows, reported_total = _rows(response.json())
            pages += 1
            if reported_total is not None:
                total = reported_total if total is None else max(total, reported_total)
            for row in rows:
                parsed_listing = _parse(row, query)
                if parsed_listing and parsed_listing.listing_id not in seen:
                    seen.add(parsed_listing.listing_id)
                    output.append(parsed_listing)
            if not rows or len(rows) < PAGE_SIZE:
                break
            if total is not None and offset + len(rows) >= total:
                break
            if offset + PAGE_SIZE >= RESULT_CAP:
                return CollectionResult(SOURCE, output, False, True, scope_key, pages, "result_cap_reached", total)
        else:
            return CollectionResult(SOURCE, output, False, True, scope_key, pages, "max_pages_reached", total)
        return CollectionResult(SOURCE, output, True, False, scope_key, pages, total=total)
    except Exception as exc:
        return CollectionResult(SOURCE, output, False, page_attempted, scope_key, pages, str(exc), total)


collect_vivareal = collect
