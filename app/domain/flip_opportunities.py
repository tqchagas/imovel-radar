"""Strict market-listing rules for the Belo Horizonte flip garimpo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median

from app.domain.slugs import address_key, street_key

PRIORITY_NEIGHBORHOODS = (
    "alto_barroca",
    "barroca",
    "nova_suica",
    "santo_agostinho",
    "lourdes",
    "funcionarios",
    "savassi",
)
COMPLEMENTARY_NEIGHBORHOODS = (
    "sion",
    "anchieta",
    "cruzeiro",
    "serra",
    "santo_antonio",
    "gutierrez",
    "prado",
    "sao_pedro",
)
ALLOWED_NEIGHBORHOODS = frozenset(
    PRIORITY_NEIGHBORHOODS + COMPLEMENTARY_NEIGHBORHOODS
)
AREA_BANDS = ((30.0, 60.0), (60.0, 90.0), (90.0, 130.0), (130.0, 350.0))
MIN_COMPARABLES = 5
MAX_PRICE = 700_000.0


@dataclass(frozen=True)
class FlipComparable:
    listing_id: str
    fingerprint: str | None
    bairro: str | None
    tipo_imovel: str | None
    area_m2: float | None
    price: float | None


@dataclass(frozen=True)
class FlipCandidate:
    source: str
    listing_id: str
    url: str
    bairro: str | None
    rua: str | None
    tipo_imovel: str | None
    area_m2: float | None
    bedrooms: int | None
    parking_spaces: int | None
    condominium: float | None
    price: float | None
    fingerprint: str | None
    page_verified_at: datetime | None = None
    last_seen_at: datetime | None = None


@dataclass(frozen=True)
class FlipOpportunity:
    candidate: FlipCandidate
    area_band: str
    price_per_m2: float
    reference_per_m2: float
    gap_pct: float
    status: str
    comparable_count: int


def area_band(area: float | None) -> tuple[float, float] | None:
    if area is None or area < 30 or area > 350:
        return None
    for index, bounds in enumerate(AREA_BANDS):
        low, high = bounds
        if low <= area < high or (index == len(AREA_BANDS) - 1 and area == high):
            return bounds
    return None


def area_band_label(bounds: tuple[float, float]) -> str:
    return f"{bounds[0]:.0f}–{bounds[1]:.0f} m²"


def eligible(candidate: FlipCandidate, city: str | None) -> bool:
    bairro = address_key(candidate.bairro)
    rua = street_key(candidate.rua)
    return bool(
        address_key(city) == "belo_horizonte"
        and bairro in ALLOWED_NEIGHBORHOODS
        and not (bairro == "prado" and rua and "perimetral" in rua)
        and candidate.source in {"loft", "quintoandar", "vivareal"}
        and candidate.tipo_imovel in {"APARTAMENTO", "CASA"}
        and candidate.url
        and candidate.price is not None
        and 0 < candidate.price <= MAX_PRICE
        and candidate.parking_spaces is not None
        and candidate.parking_spaces >= 1
        and area_band(candidate.area_m2) is not None
    )


def comparable_values(
    candidate: FlipCandidate,
    rows: list[FlipComparable],
) -> list[float]:
    bounds = area_band(candidate.area_m2)
    bairro = address_key(candidate.bairro)
    if bounds is None or bairro is None:
        return []

    unique: dict[str, float] = {}
    for row in rows:
        area = row.area_m2
        price = row.price
        if (
            address_key(row.bairro) != bairro
            or row.tipo_imovel != candidate.tipo_imovel
            or area is None
            or area_band(area) != bounds
            or price is None
            or price <= 0
        ):
            continue
        # The candidate's own QuintoAndar listing must not price itself.
        if (
            candidate.fingerprint
            and row.fingerprint
            and row.fingerprint == candidate.fingerprint
        ) or (row.listing_id == candidate.listing_id and candidate.source == "quintoandar"):
            continue
        fingerprint = row.fingerprint or f"quintoandar:{row.listing_id}"
        unique.setdefault(fingerprint, price / area)
    return list(unique.values())


def classify_gap(gap_pct: float) -> str:
    if gap_pct > 0.60:
        return "OUTLIER - Checar área/documentação"
    if gap_pct > 0:
        return "OPORTUNIDADE"
    return "PREÇO DE MERCADO"


def calculate_opportunity(
    candidate: FlipCandidate,
    comparables: list[FlipComparable],
    *,
    city: str,
) -> FlipOpportunity | None:
    if not eligible(candidate, city):
        return None
    values = comparable_values(candidate, comparables)
    if len(values) < MIN_COMPARABLES:
        return None
    assert candidate.area_m2 is not None and candidate.price is not None
    bounds = area_band(candidate.area_m2)
    assert bounds is not None
    candidate_m2 = candidate.price / candidate.area_m2
    reference_m2 = float(median(values))
    gap = (reference_m2 - candidate_m2) / reference_m2
    return FlipOpportunity(
        candidate=candidate,
        area_band=area_band_label(bounds),
        price_per_m2=candidate_m2,
        reference_per_m2=reference_m2,
        gap_pct=gap,
        status=classify_gap(gap),
        comparable_count=len(values),
    )
