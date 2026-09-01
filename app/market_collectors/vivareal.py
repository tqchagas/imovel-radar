from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, parse_qsl, urlsplit, urlunparse, urlunsplit

from app.core.http_client import request
from app.market_collectors.normalize import canonical_scope_key, is_portal_url, listing, query_type, safe_float, safe_int
from app.market_collectors.types import CollectionResult, MarketQuery

SOURCE = "vivareal"
API_URL = "https://glue-api.vivareal.com/v4/listings"


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
    normalized_rows = [row.get("listing", row) for row in rows]
    if any(not isinstance(row, dict) for row in normalized_rows):
        raise ValueError("invalid_payload_structure")
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


def _price(row: dict[str, Any]) -> float | None:
    pricing = row.get("pricingInfos")
    if isinstance(pricing, dict):
        pricing = [pricing]
    if isinstance(pricing, list):
        for info in pricing:
            if isinstance(info, dict) and str(info.get("businessType", "")).upper() == "SALE":
                return safe_float(info.get("price") or info.get("salePrice"), positive=True)
        if any(isinstance(info, dict) and info.get("businessType") for info in pricing):
            return None
    return None


def _parse(row: dict[str, Any], query: MarketQuery):
    identifier = str(row.get("id") or row.get("externalId") or row.get("legacyId") or "").strip()
    price = _price(row)
    if not identifier or price is None:
        return None
    link = row.get("link")
    raw_url = link.get("href") if isinstance(link, dict) else link
    url = urljoin("https://www.vivareal.com.br", str(raw_url or f"/imovel/id-{identifier}/"))
    if not is_portal_url(SOURCE, url):
        return None
    url_parts = urlsplit(url)
    url = urlunsplit((url_parts.scheme, url_parts.netloc, url_parts.path, "", ""))
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    point = address.get("point") if isinstance(address.get("point"), dict) else {}
    areas = row.get("usableAreas") or []
    bedrooms = row.get("bedrooms")
    bathrooms = row.get("bathrooms")
    suites = row.get("suites")
    parking = row.get("parkingSpaces")
    approximate = point.get("lat") is None and point.get("approximateLat") is not None
    parsed = listing(SOURCE, query, row, listing_id=identifier, url=url, cidade=address.get("city"), bairro=address.get("neighborhood") or query.bairro, rua=address.get("street") or address.get("streetName"), numero=address.get("streetNumber"), tipo_imovel=(row.get("unitTypes") or [row.get("propertyType")])[0], quartos=bedrooms[0] if isinstance(bedrooms, list) and bedrooms else bedrooms, bathrooms=bathrooms[0] if isinstance(bathrooms, list) and bathrooms else bathrooms, suites=suites[0] if isinstance(suites, list) and suites else suites, parking_spaces=parking[0] if isinstance(parking, list) and parking else parking, area_util_m2=areas[0] if isinstance(areas, list) and areas else None, preco_total=price, lat=point.get("lat") or point.get("approximateLat"), lon=point.get("lon") or point.get("approximateLon"), coordinate_source="APPROXIMATE" if approximate else "VIVAREAL_POINT" if point.get("lat") is not None else None)
    return parsed if parsed.tipo_imovel else None


def collect(query: MarketQuery) -> CollectionResult:
    limit = max(1, query.max_pages or 100)
    output = []
    seen: set[str] = set()
    pages = 0
    page_attempted = False
    total: int | None = None
    try:
        requested_type = query_type(query.tipo_imovel)
        for page in range(1, limit + 1):
            base = os.getenv("VIVAREAL_API_URL", API_URL)
            parsed = urlparse(base)
            params = dict(parse_qsl(parsed.query, keep_blank_values=True))
            params.update({"business": "SALE", "portal": "VIVAREAL", "page": str(page), "size": "100", "from": str((page - 1) * 100)})
            if query.bairro:
                params["addressNeighborhood"] = query.bairro
            if requested_type:
                params["unitTypes"] = "HOUSE" if requested_type == "CASA" else "APARTMENT"
            if query.quartos is not None:
                params["bedrooms"] = str(query.quartos)
            if query.area_util_m2 is not None:
                params["usableAreas"] = str(query.area_util_m2)
            url = urlunparse(parsed._replace(query=urlencode(params)))
            page_attempted = True
            response = request("GET", url, headers={"accept": "application/json", "origin": "https://www.vivareal.com.br", "referer": "https://www.vivareal.com.br/", "user-agent": "Mozilla/5.0", "x-domain": ".vivareal.com.br"}, timeout=25)
            if not 200 <= int(response.status_code) < 300:
                raise RuntimeError(f"http_{response.status_code}")
            rows, reported_total = _rows(response.json())
            pages += 1
            if reported_total is not None:
                total = reported_total if total is None else max(total, reported_total)
            if not rows:
                return CollectionResult(SOURCE, output, True, False, canonical_scope_key(query, SOURCE), pages, total=total)
            for row in rows:
                parsed_listing = _parse(row, query)
                if parsed_listing and parsed_listing.listing_id not in seen:
                    seen.add(parsed_listing.listing_id)
                    output.append(parsed_listing)
            if total is not None and len(seen) >= total:
                return CollectionResult(SOURCE, output, True, False, canonical_scope_key(query, SOURCE), pages, total=total)
            if total is None and len(rows) < 100:
                return CollectionResult(SOURCE, output, True, False, canonical_scope_key(query, SOURCE), pages, total=total)
        return CollectionResult(SOURCE, output, False, True, canonical_scope_key(query, SOURCE), pages, "max_pages_reached", total)
    except Exception as exc:
        return CollectionResult(SOURCE, output, False, page_attempted, canonical_scope_key(query, SOURCE), pages, str(exc), total)


collect_vivareal = collect
