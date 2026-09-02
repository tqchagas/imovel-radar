from __future__ import annotations

import os
import re
import uuid
from typing import Any

from app.core.http_client import request
from app.market_collectors.normalize import (
    canonical_scope_key,
    is_portal_url,
    listing,
    parse_iso_datetime,
    query_type,
    safe_float,
    safe_int,
)
from app.market_collectors.types import CollectionResult, MarketQuery

SOURCE = "loft"
API_URL = "https://landscape-api.loft.com.br/listing/v4/search"

# hitsPerPage above 100 is accepted but silently truncates the page (500 asked
# for 622 cards returns 122 and then an empty page 2), and 150 times out.
# Anything at or past RESULT_CAP comes back empty; one page further answers 500.
PAGE_SIZE = 100
RESULT_CAP = 9000

HOME_TYPE = {"CASA": "house", "APARTAMENTO": "apartment"}
RESIDENTIAL = "residential"


def _rows(payload: Any) -> tuple[list[dict[str, Any]], int | None, int | None]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload_structure")
    rows = payload.get("listings")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid_payload_structure")
    extracted = [row.get("listing", row) for row in rows]
    if any(not isinstance(row, dict) for row in extracted):
        raise ValueError("invalid_payload_structure")
    pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
    # Rows are cards: several listings of the same unit collapse into one, and
    # that collapsing happens after the page is sliced. A page can therefore
    # come back far shorter than hitsPerPage while more pages still exist, so
    # only totalPages can say when the scope is exhausted.
    return extracted, safe_int(pagination.get("totalCards")), safe_int(pagination.get("totalPages"))


# 31% dos anúncios do Loft chegam sem `area`, e nesses o cálculo de oportunidade
# nem roda. Em 60% deles a metragem está na descrição — mas o texto é ambíguo:
# validado contra os 721 anúncios que publicam área, ele acerta 87% e erra 13%,
# quase sempre por nomear uma parte ("73 m² interna + 87 m² terraço", onde o
# portal publica a soma). O erro puxa a área para baixo, o que infla o R$/m²
# pedido, então a origem viaja junto e quem consome decide se confia.
_MEDIDA = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*m\s*(?:²|2\b)", re.IGNORECASE)
_CONTEXTO_RUIM = re.compile(
    r"lazer|comum|terreno|condom[íi]nio|sal[ãa]o|piscina|churrasq|quadra|academia|"
    r"playground|garagem|vaga|dep[óo]sito",
    re.IGNORECASE,
)
_AREA_MINIMA = 20.0
_AREA_MAXIMA = 600.0


def _area_da_descricao(texto: Any) -> float | None:
    """Primeira metragem plausível do texto, ignorando as do prédio."""
    descricao = str(texto or "")
    for encontro in _MEDIDA.finditer(descricao):
        try:
            valor = float(encontro.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            continue
        if not _AREA_MINIMA <= valor <= _AREA_MAXIMA:
            continue
        vizinhanca = descricao[max(0, encontro.start() - 40):encontro.end() + 25]
        if _CONTEXTO_RUIM.search(vizinhanca):
            continue
        return valor
    return None


def _coordinate(value: Any) -> float | None:
    """Loft sends lat/lng as strings with more decimals than safe_float takes."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if -180 <= number <= 180 else None


def _parse(row: dict[str, Any], query: MarketQuery):
    identifier = str(row.get("id") or row.get("objectID") or "").strip()
    price = safe_float(row.get("price"), positive=True)
    if not identifier or price is None:
        return None
    # Land lots and commercial units share the endpoint; they have no ITBI
    # residential counterpart to compare against.
    usage = str(row.get("usageType") or "").strip().lower()
    if usage and usage != RESIDENTIAL:
        return None
    url = f"https://loft.com.br/imovel/{identifier}"
    if not is_portal_url(SOURCE, url):
        return None
    area = safe_float(row.get("area"), positive=True)
    area_origem = "portal" if area is not None else None
    if area is None:
        area = _area_da_descricao(row.get("description"))
        area_origem = "descricao" if area is not None else None

    address = row.get("address") if isinstance(row.get("address"), dict) else {}
    # The search payload never carries the street number or the postal code,
    # so this source can only ever match ITBI at street level.
    parsed = listing(
        SOURCE,
        query,
        row,
        listing_id=identifier,
        url=url,
        cidade=address.get("city"),
        bairro=address.get("neighborhood"),
        rua=address.get("streetName") or address.get("streetFullName"),
        numero=address.get("number"),
        tipo_imovel=row.get("homeType"),
        quartos=row.get("bedrooms"),
        area_util_m2=area,
        area_origem=area_origem,
        preco_total=price,
        lat=_coordinate(address.get("lat")),
        lon=_coordinate(address.get("lng")),
        coordinate_source="LOFT_GEOLOC" if _coordinate(address.get("lat")) is not None else None,
        anunciado_em=parse_iso_datetime(row.get("createdAt")),
        # `monthlyExpenses` e a soma dos dois; guardamos as parcelas.
        condominium_value=row.get("complexFee"),
        iptu_value=row.get("propertyTax"),
        bathrooms=row.get("restrooms"),
        suites=row.get("suits"),
        parking_spaces=row.get("parkingSpots"),
    )
    return parsed if parsed.tipo_imovel else None


def _payload(query: MarketQuery, requested_type: str | None, page: int) -> dict[str, Any]:
    body: dict[str, Any] = {
        "orderBy": ["rankA"],
        "cities": [f"{query.cidade}, {query.uf}".lower()],
        "transactionType": ["for_sale"],
        "hitsPerPage": PAGE_SIZE,
        "page": page,
        "searchVariant": "v3",
    }
    if query.bairro:
        # Only the fully qualified form matches; the bare name returns nothing.
        body["neighborhood"] = [f"{query.bairro}, {query.cidade}, {query.uf}"]
    if requested_type:
        body["homeType"] = [HOME_TYPE[requested_type]]
    if query.quartos is not None:
        body["bedrooms"] = query.quartos
        body["exactMatchForNumericFields"] = True
    if query.area_util_m2 is not None:
        body["areaMin"] = query.area_util_m2
        body["areaMax"] = query.area_util_m2
    return body


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
        url = os.getenv("LOFT_SEARCH_API_URL", API_URL)
        for page in range(1, limit + 1):
            offset = (page - 1) * PAGE_SIZE
            if offset >= RESULT_CAP:
                return CollectionResult(SOURCE, listings, False, True, scope_key, pages, "result_cap_reached", total)
            page_attempted = True
            response = request(
                "POST",
                url,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    # Any UUID is accepted - there is no session or login.
                    "loftUserId": str(uuid.uuid4()),
                    # The only header the gateway checks; without it, 403.
                    "Origin": "https://loft.com.br",
                },
                json_body=_payload(query, requested_type, page),
                timeout=25,
            )
            if not 200 <= int(response.status_code) < 300:
                raise RuntimeError(f"http_{response.status_code}")
            rows, reported_total, total_pages = _rows(response.json())
            pages += 1
            if reported_total is not None:
                total = reported_total if total is None else max(total, reported_total)
            for row in rows:
                parsed = _parse(row, query)
                if parsed and parsed.listing_id not in seen:
                    seen.add(parsed.listing_id)
                    listings.append(parsed)
            if total_pages is not None:
                if page >= total_pages:
                    break
            elif not rows:
                break
            if offset + PAGE_SIZE >= RESULT_CAP:
                return CollectionResult(SOURCE, listings, False, True, scope_key, pages, "result_cap_reached", total)
        else:
            return CollectionResult(SOURCE, listings, False, True, scope_key, pages, "max_pages_reached", total)
        return CollectionResult(SOURCE, listings, True, False, scope_key, pages, total=total)
    except Exception as exc:
        return CollectionResult(SOURCE, listings, False, page_attempted, scope_key, pages, str(exc), total)


collect_loft = collect
