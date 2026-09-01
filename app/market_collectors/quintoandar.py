from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from app.core.http_client import request
from app.market_collectors.normalize import canonical_scope_key, is_portal_url, listing, query_type, safe_float, safe_int, slug
from app.market_collectors.types import CollectionResult, MarketQuery

SOURCE = "quintoandar"
API_URL = "https://apigw.prod.quintoandar.com.br/house-listing-search/v2/search/list"


def _rows(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload_structure")
    result = payload.get("search", {}).get("result", {}) if isinstance(payload.get("search"), dict) else {}
    candidates = (payload.get("hits"), payload.get("items"), result.get("hits"), result.get("items"))
    rows = next((candidate for candidate in candidates if candidate is not None), None)
    total = _first_total(_total(payload.get("total")), _total(payload.get("totalCount")))
    total = _first_total(total, _total(payload.get("pagination")), _total(result.get("total")), _total(result.get("totalCount")))
    if isinstance(rows, dict):
        total = _first_total(total, _total(rows.get("total")), _total(rows.get("totalCount")))
        rows = rows.get("hits") if "hits" in rows else rows.get("items")
    if not isinstance(rows, list):
        raise ValueError("invalid_payload_structure")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid_payload_structure")
    extracted = [row.get("_source", row) for row in rows]
    if any(not isinstance(row, dict) for row in extracted):
        raise ValueError("invalid_payload_structure")
    return extracted, total


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


def _parse(row: dict[str, Any], query: MarketQuery):
    identifier = str(row.get("id") or "").strip()
    price = safe_float(row.get("salePrice"), positive=True)
    if not identifier or price is None:
        return None
    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    if isinstance(row.get("address"), str):
        parts = [part.strip() for part in re.split(r"[,·]", row["address"]) if part.strip()]
        address = {"street": parts[0] if parts else row["address"], "city": parts[-1] if len(parts) > 1 else None}
    url = str(row.get("url") or row.get("slug") or "").strip()
    if not url:
        url = f"/imovel/{identifier}"
    url = urljoin("https://www.quintoandar.com.br", url)
    if not is_portal_url(SOURCE, url):
        return None
    url_parts = urlsplit(url)
    path = url_parts.path.rstrip("/")
    if not path.endswith("/comprar"):
        path += "/comprar"
    url = urlunsplit((url_parts.scheme, url_parts.netloc, path, "", ""))
    lat = row.get("latitude") or row.get("lat")
    lon = row.get("longitude") or row.get("lon")
    parsed = listing(SOURCE, query, row, listing_id=identifier, url=url, cidade=address.get("city"), bairro=row.get("neighbourhood"), rua=address.get("street"), numero=address.get("number"), tipo_imovel=row.get("type"), quartos=row.get("bedrooms") or row.get("rooms"), area_util_m2=row.get("area"), preco_total=price, lat=lat, lon=lon, coordinate_source="QUINTOANDAR_FIELDS" if lat is not None and lon is not None else None, bathrooms=row.get("bathrooms"), suites=row.get("suites"), parking_spaces=row.get("parkingSpaces"))
    return parsed if parsed.tipo_imovel else None


def collect(query: MarketQuery) -> CollectionResult:
    limit = max(1, query.max_pages or 100)
    listings = []
    seen: set[str] = set()
    pages = 0
    page_attempted = False
    total: int | None = None
    try:
        requested_type = query_type(query.tipo_imovel)
        for page in range(1, limit + 1):
            filters: dict[str, Any] = {"businessContext": "SALE"}
            if requested_type:
                filters["propertyType"] = "HOUSE" if requested_type == "CASA" else "APARTMENT"
            if query.quartos is not None:
                filters["bedrooms"] = query.quartos
            if query.area_util_m2 is not None:
                filters["area"] = query.area_util_m2
            location = f"{slug(query.bairro)}-" if query.bairro else ""
            payload = {"slug": f"{location}{slug(query.cidade)}-{query.uf.lower()}-brasil", "filters": filters, "pagination": {"pageSize": 100, "offset": (page - 1) * 100}}
            page_attempted = True
            response = request("POST", os.getenv("QUINTOANDAR_SEARCH_API_URL", API_URL), headers={"accept": "application/json", "content-type": "application/json", "origin": "https://www.quintoandar.com.br", "user-agent": "Mozilla/5.0"}, json_body=payload, timeout=25)
            if not 200 <= int(response.status_code) < 300:
                raise RuntimeError(f"http_{response.status_code}")
            rows, reported_total = _rows(response.json())
            pages += 1
            if reported_total is not None:
                total = reported_total if total is None else max(total, reported_total)
            if not rows:
                return CollectionResult(SOURCE, listings, True, False, canonical_scope_key(query, SOURCE), pages, total=total)
            for row in rows:
                parsed = _parse(row, query)
                if parsed and parsed.listing_id not in seen:
                    seen.add(parsed.listing_id)
                    listings.append(parsed)
            if total is not None and len(seen) >= total:
                return CollectionResult(SOURCE, listings, True, False, canonical_scope_key(query, SOURCE), pages, total=total)
            if total is None and len(rows) < 100:
                return CollectionResult(SOURCE, listings, True, False, canonical_scope_key(query, SOURCE), pages, total=total)
        return CollectionResult(SOURCE, listings, False, True, canonical_scope_key(query, SOURCE), pages, "max_pages_reached", total)
    except Exception as exc:
        return CollectionResult(SOURCE, listings, False, page_attempted, canonical_scope_key(query, SOURCE), pages, str(exc), total)


collect_quintoandar = collect
