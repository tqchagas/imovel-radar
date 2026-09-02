from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MarketQuery:
    uf: str
    cidade: str
    bairro: str | None = None
    tipo_imovel: str | None = None
    quartos: int | None = None
    area_util_m2: float | None = None
    max_pages: int | None = None
    source: str | None = None
    bairros: tuple[str, ...] = ()
    filtros: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedListing:
    source: str
    listing_id: str
    url: str
    uf: str
    cidade: str
    bairro: str | None = None
    rua: str | None = None
    numero: str | None = None
    tipo_imovel: str | None = None
    quartos: int | None = None
    bathrooms: int | None = None
    suites: int | None = None
    parking_spaces: int | None = None
    area_util_m2: float | None = None
    preco_total: float | None = None
    lat: float | None = None
    lon: float | None = None
    coordinate_source: str | None = None
    # "portal" quando a fonte publica a área, "descricao" quando ela foi lida do
    # texto livre do anúncio — que discorda do número publicado em ~13% dos
    # casos, quase sempre nomeando uma parte (interna, terraço) em vez do total.
    area_origem: str | None = None
    # Quando o portal publicou o anuncio. Metade do estoque do Loft esta no ar
    # ha mais de um ano, e desconto em anuncio parado e preco que o mercado ja
    # recusou — sem a data nao ha como distinguir os dois casos.
    anunciado_em: datetime | None = None
    condominium_value: float | None = None
    iptu_value: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionResult:
    source: str
    listings: list[NormalizedListing]
    success: bool
    partial: bool
    scope_key: str
    pages: int
    error: str | None = None
    total: int | None = None
