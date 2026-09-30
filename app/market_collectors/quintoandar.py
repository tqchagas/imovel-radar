"""Imóvel Radar adapter for the standalone ``quintoandar`` module."""

from __future__ import annotations

from app.core.http_client import request
from app.market_collectors.normalize import canonical_scope_key, listing, query_type
from app.market_collectors.types import CollectionResult, MarketQuery, NormalizedListing
from quintoandar import QuintoAndarClient, SearchQuery
from quintoandar.search import API_URL, FIELDS, PAGE_SIZE, RESULT_CAP, parse_record

SOURCE = "quintoandar"


def _search_query(query: MarketQuery) -> SearchQuery:
    property_type = query.tipo_imovel or query.filtros.get("tipo_imovel")
    return SearchQuery(
        city=query.cidade,
        state=query.uf,
        neighborhood=query.bairro,
        property_type=query_type(property_type),
        bedrooms=query.quartos if query.quartos is not None else query.filtros.get("quartos"),
        area_m2=query.area_util_m2 if query.area_util_m2 is not None else query.filtros.get("area_util_m2"),
    )


def _parse(row: dict, query: MarketQuery) -> NormalizedListing | None:
    """Compatibility adapter: convert one package DTO to the app's storage DTO."""
    parsed = parse_record(row, _search_query(query))
    if parsed is None:
        return None
    return listing(
        SOURCE,
        query,
        parsed.raw,
        listing_id=parsed.listing_id,
        url=parsed.url,
        uf=parsed.state,
        cidade=parsed.city,
        bairro=parsed.neighborhood,
        rua=parsed.street,
        numero=None,
        tipo_imovel=parsed.property_type,
        quartos=parsed.bedrooms,
        bathrooms=parsed.bathrooms,
        suites=parsed.suites,
        parking_spaces=parsed.parking_spaces,
        area_util_m2=parsed.area_m2,
        preco_total=parsed.price,
        lat=parsed.latitude,
        lon=parsed.longitude,
        coordinate_source="QUINTOANDAR_LOCATION" if parsed.latitude is not None else None,
        condo_id=parsed.condo_id,
        condo_name=parsed.condo_name,
        iptu_value=parsed.iptu,
        condominium_value=parsed.condominium,
    )


def collect(query: MarketQuery) -> CollectionResult:
    scope_key = canonical_scope_key(query, SOURCE)
    try:
        result = QuintoAndarClient(request).search_listings(
            _search_query(query), max_pages=query.max_pages or 100, api_url=API_URL
        )
    except Exception as error:
        return CollectionResult(SOURCE, [], False, False, scope_key, 0, str(error))
    listings = [
        listing(
            SOURCE,
            query,
            item.raw,
            listing_id=item.listing_id,
            url=item.url,
            uf=item.state,
            cidade=item.city,
            bairro=item.neighborhood,
            rua=item.street,
            numero=None,
            tipo_imovel=item.property_type,
            quartos=item.bedrooms,
            bathrooms=item.bathrooms,
            suites=item.suites,
            parking_spaces=item.parking_spaces,
            area_util_m2=item.area_m2,
            preco_total=item.price,
            lat=item.latitude,
            lon=item.longitude,
            coordinate_source="QUINTOANDAR_LOCATION" if item.latitude is not None else None,
            condo_id=item.condo_id,
            condo_name=item.condo_name,
            iptu_value=item.iptu,
            condominium_value=item.condominium,
        )
        for item in result.listings
    ]
    return CollectionResult(
        SOURCE, listings, result.success, result.partial, scope_key,
        result.pages, result.error, result.total,
    )


collect_quintoandar = collect
