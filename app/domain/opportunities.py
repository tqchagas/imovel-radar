"""Pure calculation of listing opportunities against recent ITBI transactions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Iterable, Sequence

from app.domain.market_stats import Sale, shift_months
from app.domain.slugs import address_key
from app.market_collectors.normalize import normalize_type

WINDOW_MONTHS = 24
AREA_TOLERANCE = 0.30
EXACT_MIN_SAMPLE = 5
BAIRRO_AREA_MIN_SAMPLE = 15
BAIRRO_AMPLO_MIN_SAMPLE = 1
MIN_DISCOUNT_PCT = 0.15
MIN_CONFIDENCE = "media"

RESIDENTIAL_OCCUPATION = "RESIDENCIAL"
TYPE_TO_CONSTRUCTION = {"APARTAMENTO": "AP", "CASA": "CA"}
REFERENCE_CONFIDENCE = {
    "endereco_exato": "alta",
    "bairro_area": "media",
    "bairro_amplo": "baixa",
}
CONFIDENCE_ORDER = {"baixa": 0, "media": 1, "alta": 2}
REFERENCE_LABEL = {
    "endereco_exato": "endereço exato",
    "bairro_area": "bairro e faixa de área",
    "bairro_amplo": "bairro amplo",
}


def itbi_construction_type(tipo_imovel: str | None) -> str | None:
    """Map a listing type to the ITBI residential construction code."""
    return TYPE_TO_CONSTRUCTION.get(normalize_type(tipo_imovel) or "")


@dataclass(frozen=True)
class ListingInput:
    source: str
    listing_id: str
    tipo_imovel: str | None
    area_util_m2: float | None
    preco_total: float | None
    bairro: str | None = None
    rua: str | None = None
    numero: str | None = None


@dataclass(frozen=True)
class Reference:
    tipo_referencia: str
    confianca: str
    amostra_count: int
    preco_m2_mediano: float
    referencia_data_inicio: date
    referencia_data_fim: date
    area_minima: float | None
    area_maxima: float | None


@dataclass(frozen=True)
class Opportunity:
    source: str
    listing_id: str
    preco_anunciado: float
    preco_estimado: float
    desconto_pct: float
    desconto_reais: float
    tipo_referencia: str
    confianca: str
    amostra_count: int
    referencia_data_inicio: date
    referencia_data_fim: date
    preco_m2_mediano: float
    motivos: tuple[str, ...]
    fingerprint: str


def _positive(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if number > 0 else None


def is_valid_sale(sale: Sale) -> bool:
    """Residential ITBI row with a usable declared value and built area."""
    return (
        (sale.occupation_type or "").strip().upper() == RESIDENTIAL_OCCUPATION
        and _positive(sale.declared_value) is not None
        and _positive(sale.built_area_acquired) is not None
    )


def sale_price_per_m2(sale: Sale) -> float:
    return float(sale.declared_value) / float(sale.built_area_acquired)


def reference_date_for(sales: Iterable[Sale]) -> date | None:
    """Latest settlement date among valid residential ITBI rows."""
    dates = [sale.settlement_date for sale in sales if is_valid_sale(sale)]
    return max(dates) if dates else None


def window_bounds(reference: date) -> tuple[date, date]:
    """Inclusive 24-month window ending on the reference date."""
    return shift_months(reference, WINDOW_MONTHS), reference


def _candidates(
    listing: ListingInput, sales: Sequence[Sale], reference: date
) -> tuple[list[Sale], str | None]:
    construction_type = itbi_construction_type(listing.tipo_imovel)
    bairro = address_key(listing.bairro)
    if construction_type is None or bairro is None:
        return [], construction_type
    start, end = window_bounds(reference)
    selected = [
        sale
        for sale in sales
        if is_valid_sale(sale)
        and (sale.construction_type or "").strip().upper() == construction_type
        and address_key(sale.neighborhood) == bairro
        and start <= sale.settlement_date <= end
    ]
    return selected, construction_type


def _within_area(sale: Sale, area: float) -> bool:
    return area * (1 - AREA_TOLERANCE) <= float(sale.built_area_acquired) <= area * (1 + AREA_TOLERANCE)


def _same_address(sale: Sale, rua: str | None, numero: str | None) -> bool:
    if rua is None or numero is None:
        return False
    return address_key(sale.street) == rua and address_key(sale.street_number) == numero


def _reference_from(sales: Sequence[Sale], tipo: str, area_range: tuple[float, float] | None) -> Reference:
    return Reference(
        tipo_referencia=tipo,
        confianca=REFERENCE_CONFIDENCE[tipo],
        amostra_count=len(sales),
        preco_m2_mediano=median(sale_price_per_m2(sale) for sale in sales),
        referencia_data_inicio=min(sale.settlement_date for sale in sales),
        referencia_data_fim=max(sale.settlement_date for sale in sales),
        area_minima=round(area_range[0], 2) if area_range else None,
        area_maxima=round(area_range[1], 2) if area_range else None,
    )


def select_reference(
    listing: ListingInput, sales: Sequence[Sale], reference: date
) -> Reference | None:
    """Pick the ITBI sample in the exact order defined by the specification."""
    candidates, _ = _candidates(listing, sales, reference)
    if not candidates:
        return None

    area = _positive(listing.area_util_m2)
    area_range = (area * (1 - AREA_TOLERANCE), area * (1 + AREA_TOLERANCE)) if area else None
    in_area = [sale for sale in candidates if area and _within_area(sale, area)]

    rua = address_key(listing.rua)
    numero = address_key(listing.numero)
    exact = [sale for sale in in_area if _same_address(sale, rua, numero)]
    if len(exact) >= EXACT_MIN_SAMPLE:
        return _reference_from(exact, "endereco_exato", area_range)

    if len(in_area) >= BAIRRO_AREA_MIN_SAMPLE:
        return _reference_from(in_area, "bairro_area", area_range)

    if len(candidates) >= BAIRRO_AMPLO_MIN_SAMPLE:
        return _reference_from(candidates, "bairro_amplo", None)
    return None


def fingerprint(
    *,
    source: str,
    listing_id: str,
    preco_anunciado: float,
    preco_estimado: float,
    desconto_pct: float,
    tipo_referencia: str,
    confianca: str,
    amostra_count: int,
    referencia_data_inicio: date,
    referencia_data_fim: date,
) -> str:
    """Stable digest of everything that makes an alert worth resending."""
    payload = {
        "source": source,
        "listing_id": listing_id,
        "preco_anunciado": round(float(preco_anunciado), 2),
        "preco_estimado": round(float(preco_estimado), 2),
        "desconto_pct": round(float(desconto_pct), 4),
        "tipo_referencia": tipo_referencia,
        "confianca": confianca,
        "amostra_count": int(amostra_count),
        "referencia_data_inicio": referencia_data_inicio.isoformat(),
        "referencia_data_fim": referencia_data_fim.isoformat(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _money(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {formatted}"


def _area(value: float) -> str:
    return f"{value:.2f}".replace(".", ",") + " m²"


def _motivos(listing: ListingInput, reference: Reference, area: float) -> tuple[str, ...]:
    escopo = REFERENCE_LABEL[reference.tipo_referencia]
    if reference.tipo_referencia == "endereco_exato":
        onde = f"{escopo} ({listing.rua}, {listing.numero})"
    elif reference.tipo_referencia == "bairro_area":
        onde = f"{escopo} no bairro {listing.bairro}"
    else:
        onde = f"{escopo} no bairro {listing.bairro}, sem filtro de área"
    motivos = [
        f"Mediana de {reference.amostra_count} ITBIs residenciais por {onde}.",
        f"Janela de {WINDOW_MONTHS} meses entre "
        f"{reference.referencia_data_inicio.isoformat()} e {reference.referencia_data_fim.isoformat()}.",
        f"Referência de {_money(reference.preco_m2_mediano)}/m² aplicada a {_area(area)}.",
    ]
    if reference.area_minima is not None and reference.area_maxima is not None:
        motivos.append(
            f"Área comparável entre {_area(reference.area_minima)} e {_area(reference.area_maxima)}."
        )
    if reference.confianca == "baixa":
        motivos.append("Amostra insuficiente para endereço ou faixa de área: confiança baixa.")
    return tuple(motivos)


def compute_opportunity(
    listing: ListingInput,
    sales: Sequence[Sale],
    reference_date: date | None = None,
) -> Opportunity | None:
    """Estimate the fair price of a listing and the discount it offers."""
    area = _positive(listing.area_util_m2)
    preco_anunciado = _positive(listing.preco_total)
    if area is None or preco_anunciado is None:
        return None

    reference_day = reference_date or reference_date_for(sales)
    if reference_day is None:
        return None

    reference = select_reference(listing, sales, reference_day)
    if reference is None:
        return None

    preco_estimado = round(reference.preco_m2_mediano * area, 2)
    if preco_estimado <= 0:
        return None
    desconto_pct = round((preco_estimado - preco_anunciado) / preco_estimado, 4)
    desconto_reais = round(preco_estimado - preco_anunciado, 2)
    return Opportunity(
        source=listing.source,
        listing_id=listing.listing_id,
        preco_anunciado=round(preco_anunciado, 2),
        preco_estimado=preco_estimado,
        desconto_pct=desconto_pct,
        desconto_reais=desconto_reais,
        tipo_referencia=reference.tipo_referencia,
        confianca=reference.confianca,
        amostra_count=reference.amostra_count,
        referencia_data_inicio=reference.referencia_data_inicio,
        referencia_data_fim=reference.referencia_data_fim,
        preco_m2_mediano=round(reference.preco_m2_mediano, 2),
        motivos=_motivos(listing, reference, area),
        fingerprint=fingerprint(
            source=listing.source,
            listing_id=listing.listing_id,
            preco_anunciado=preco_anunciado,
            preco_estimado=preco_estimado,
            desconto_pct=desconto_pct,
            tipo_referencia=reference.tipo_referencia,
            confianca=reference.confianca,
            amostra_count=reference.amostra_count,
            referencia_data_inicio=reference.referencia_data_inicio,
            referencia_data_fim=reference.referencia_data_fim,
        ),
    )


def is_alert_eligible(
    opportunity: Opportunity | None,
    *,
    min_discount_pct: float = MIN_DISCOUNT_PCT,
    min_confianca: str = MIN_CONFIDENCE,
) -> bool:
    """An opportunity only becomes an alert with enough discount and confidence."""
    if opportunity is None:
        return False
    minimum = CONFIDENCE_ORDER.get(min_confianca, CONFIDENCE_ORDER[MIN_CONFIDENCE])
    return (
        opportunity.desconto_pct >= min_discount_pct
        and CONFIDENCE_ORDER[opportunity.confianca] >= minimum
    )
