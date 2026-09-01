from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, parse_qsl, urlunparse

from app.core.http_client import request
from app.market_collectors.normalize import canonical_scope_key, listing, safe_float, safe_int
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
    total = safe_int(meta.get("total") or payload.get("total"))
    if total is None and isinstance(search, dict):
        total = safe_int(search.get("total"))
    return [row.get("listing", row) for row in rows if isinstance(row, dict)], total


def _price(row: dict[str, Any]) -> float | None:
    pricing = row.get("pricingInfos")
    if isinstance(pricing, dict):
        pricing = [pricing]
    if isinstance(pricing, list):
        for info in pricing:
            if isinstance(info, dict) and str(info.get("businessType", "")).upper() == "SALE":
                return safe_float(info.get("price") or info.get("salePrice"))
        if any(isinstance(info, dict) and info.get("businessType") for info in pricing):
            return None
    return safe_float(row.get("price") or row.get("salePrice"))


def _parse(row: dict[str, Any], query: MarketQuery):
    identifier = str(row.get("id") or row.get("externalId") or row.get("legacyId") or "").strip()
    price = _price(row)
    if not identifier or price is None:
        return None
    link = row.get("link")
    raw_url = link.get("href") if isinstance(link, dict) else link
    url = urljoin("https://www.vivareal.com.br", str(raw_url or f"/imovel/id-{identifier}/"))
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    point = address.get("point") if isinstance(address.get("point"), dict) else {}
    areas = row.get("usableAreas") or row.get("totalAreas") or []
    bedrooms = row.get("bedrooms")
    bathrooms = row.get("bathrooms")
    suites = row.get("suites")
    parking = row.get("parkingSpaces")
    return listing(SOURCE, query, row, listing_id=identifier, url=url, cidade=address.get("city"), bairro=address.get("neighborhood") or query.bairro, rua=address.get("street") or address.get("streetName"), numero=address.get("streetNumber"), tipo_imovel=(row.get("unitTypes") or [row.get("propertyType")])[0], quartos=bedrooms[0] if isinstance(bedrooms, list) and bedrooms else bedrooms, bathrooms=bathrooms[0] if isinstance(bathrooms, list) and bathrooms else bathrooms, suites=suites[0] if isinstance(suites, list) and suites else suites, parking_spaces=parking[0] if isinstance(parking, list) and parking else parking, area_util_m2=areas[0] if isinstance(areas, list) and areas else None, preco_total=price, lat=point.get("lat") or point.get("approximateLat"), lon=point.get("lon") or point.get("approximateLon"), coordinate_source="VIVAREAL_POINT" if point.get("lat") is not None else None)


def collect(query: MarketQuery) -> CollectionResult:
    limit = max(1, query.max_pages or 100)
    output = []
    seen: set[str] = set()
    pages = 0
    try:
        for page in range(1, limit + 1):
            base = os.getenv("VIVAREAL_API_URL", API_URL)
            parsed = urlparse(base)
            params = dict(parse_qsl(parsed.query, keep_blank_values=True))
            params.update({"business": "SALE", "portal": "VIVAREAL", "page": str(page), "size": "100", "from": str((page - 1) * 100)})
            url = urlunparse(parsed._replace(query=urlencode(params)))
            response = request("GET", url, headers={"accept": "application/json", "origin": "https://www.vivareal.com.br", "referer": "https://www.vivareal.com.br/", "user-agent": "Mozilla/5.0", "x-domain": ".vivareal.com.br"}, timeout=25)
            if not 200 <= int(response.status_code) < 300:
                raise RuntimeError(f"http_{response.status_code}")
            rows, total = _rows(response.json())
            pages += 1
            if not rows:
                return CollectionResult(SOURCE, output, True, False, canonical_scope_key(query, SOURCE), pages)
            for row in rows:
                parsed_listing = _parse(row, query)
                if parsed_listing and parsed_listing.listing_id not in seen:
                    seen.add(parsed_listing.listing_id)
                    output.append(parsed_listing)
            if total is not None and len(seen) >= total:
                return CollectionResult(SOURCE, output, True, False, canonical_scope_key(query, SOURCE), pages)
            if total is None and len(rows) < 100:
                return CollectionResult(SOURCE, output, True, False, canonical_scope_key(query, SOURCE), pages)
        return CollectionResult(SOURCE, output, False, True, canonical_scope_key(query, SOURCE), pages, "max_pages_reached")
    except Exception as exc:
        return CollectionResult(SOURCE, output, False, pages > 0, canonical_scope_key(query, SOURCE), pages, str(exc))


collect_vivareal = collect
