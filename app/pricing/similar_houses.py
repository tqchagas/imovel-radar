"""Contexto de mercado do QuintoAndar, para qualquer fonte.

O `price-suggestion` avalia uma unidade específica e resolve tudo pelo id do
anúncio, então só serve para anúncios do próprio QuintoAndar. Este endpoint
pergunta por coordenada, tamanho e cômodos — nenhum id — e responde para Loft e
VivaReal também, inclusive sem sessão.

O que ele devolve é a vizinhança, não uma avaliação: R$/m² de anúncios ativos,
R$/m² de imóveis já fora do mercado (mais perto de transação que de pedido) e a
média de dias até fechar negócio na região. Serve de contexto — um apartamento
pode estar abaixo da média do bairro porque é pior, e a média não sabe disso.
Por isso não entra na nota.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.http_client import PortalBlocked
from app.core.http_client import request as default_request
from app.models.market_comparable import MarketComparable
from quintoandar import QuintoAndarClient
from quintoandar.errors import PortalBlocked as PackagePortalBlocked
from quintoandar.similar import (
    HEADERS,
    MIN_INTERVAL_SECONDS,
    URL,
    build_market_body as _build_market_body,
    extract_summary as _extract_summary,
)

logger = logging.getLogger(__name__)

# A faixa de preço filtra os comparáveis. Enviar a faixa do próprio anúncio
# devolve a média de quem já está naquele preço, o que é circular: medido no
# mesmo imóvel, pedido ±10% respondeu 12.280/m², metade do preço respondeu
# 5.720 e o dobro respondeu 22.460. Com faixa larga o filtro deixa de morder e
# a resposta vira o entorno de verdade.
BANDA_INFERIOR = 0.2
BANDA_SUPERIOR = 5.0

BLOCKED_STATUS = frozenset({401, 403, 429})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def build_body(row: MarketComparable) -> dict[str, Any] | None:
    """Corpo da consulta, ou None quando o anúncio não tem coordenada."""
    preco = _float(row.preco_total)
    area = _float(row.area_util_m2)
    if row.lat is None or row.lon is None or preco is None or area is None:
        return None
    return _build_market_body(
        price=preco,
        area_m2=area,
        latitude=float(row.lat),
        longitude=float(row.lon),
        bedrooms=row.bedrooms,
        bathrooms=row.bathrooms,
        property_type=row.tipo_imovel,
        city=row.cidade,
        address=row.rua,
    )


def extract_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    return _extract_summary(payload)


def fetch_similar_houses(
    row: MarketComparable, *, request_fn: Callable[..., Any] = default_request
) -> dict[str, Any]:
    body = build_body(row)
    if body is None:
        raise ValueError("listing without coordinates or area")
    try:
        return QuintoAndarClient(request_fn).similar_houses(body)
    except PackagePortalBlocked as error:
        raise PortalBlocked(str(error)) from error


def similar_houses_updater(
    request_fn: Callable[..., Any] = default_request,
) -> Callable[[MarketComparable], bool]:
    """Devolve o buscador de uma linha só que o refresh injeta.

    True quando veio contexto; False quando a região não tem comparáveis — isso
    é resposta, não falha, e a data é gravada para não reperguntar antes do TTL.
    """

    def update(row: MarketComparable) -> bool:
        campos = extract_summary(fetch_similar_houses(row, request_fn=request_fn))
        for nome, valor in campos.items():
            setattr(row, nome, valor)
        row.similares_updated_at = _now()
        return campos["similares_m2_anunciado"] is not None

    return update
