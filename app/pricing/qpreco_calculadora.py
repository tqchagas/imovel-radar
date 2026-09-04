"""A Calculadora QPreço: o modelo do QuintoAndar sobre um endereço, não um anúncio.

O `price-suggestion` que este projeto já usa resolve tudo pelo id do anúncio e
responde 404 para qualquer outra coisa — medido: coordenada e atributos sem id
devolvem `"House null was not found"`. Imóvel de leilão nunca tem id.

O produto "quanto vale meu imóvel" roda o mesmo modelo a partir de atributos, e
são dois endpoints que respondem sem cookie e sem sessão. A tela deles dispara
ainda um `save-lead`, que registra o interessado no funil da empresa; ele é uma
chamada separada e **não é feita aqui**.

Coordenada é obrigatória. Sem ela o portal responde 200 dizendo que não
conseguiu calcular — a mesma resposta que dá para imóvel genuinamente atípico —,
e uma coordenada errada por duzentos metros não falha: devolve um número
plausível do quarteirão vizinho. Por isso ela é conferida por gente, nunca
geocodificada em silêncio.

Medido em 2026-09-04: Funcionários/BH devolve 4.513.000 com certeza "low",
Vila Madalena/SP 1.094.500 com "medium", Itabirito/MG 335.000 com "low".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from app.core.http_client import PortalBlocked
from app.core.http_client import request as default_request

URL_ESTIMATE = (
    "https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/"
    "brand-calculator/estimate"
)
URL_SIMILARES = (
    "https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/v1/"
    "brand-calculator/similar-houses"
)

# O mesmo ritmo do qpreço e dos similares: uma consulta é o que um humano
# preenchendo o formulário gera, e é essa ordem de grandeza que se imita.
MIN_INTERVAL_SECONDS = float(os.getenv("QPRECO_CALC_MIN_INTERVAL_SECONDS", "3.0"))
BLOCKED_STATUS = frozenset({401, 403, 429})

HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://proprietario.quintoandar.com.br",
    "referer": "https://proprietario.quintoandar.com.br/",
}


class QprecoUnavailable(RuntimeError):
    """O portal respondeu, mas sem preço.

    É a mesma resposta para coordenada ausente e para imóvel atípico demais —
    não dá para distinguir, e inventar um número seria pior do que não ter.
    """


@dataclass(frozen=True)
class EstimateInput:
    """Os atributos que o modelo lê. `total_area` é **área útil**."""

    address: str
    city: str
    latitude: float
    longitude: float
    total_area: float
    address_number: int | None = None
    neighborhood: str | None = None
    state: str | None = None
    country: str = "Brasil"
    house_type: str = "APARTMENT"
    bedroom_count: int = 2
    bathroom_count: int = 1
    suites_count: int = 0
    parking_slots: int = 0
    floor: int | None = None
    condominium_per_month: float = 0
    iptu_per_year: float = 0


@dataclass(frozen=True)
class Estimate:
    suggested_price: float
    lower_bound: float | None
    upper_bound: float | None
    limit_lower: float | None
    limit_upper: float | None
    certainty: str | None
    percentiles: dict[int, float]


@dataclass(frozen=True)
class SoldComparable:
    """Um comparável que o portal reporta como fora do mercado.

    `price` é preço de transação, e não pedido — é o que a escada de ITBI
    inteira existe para reconstruir, sem os dois meses de atraso do cartório.
    """

    house_id: int | None
    price: float
    price_m2: float | None
    total_area: float | None
    bedroom_count: int | None
    parking_slots: int | None
    distance_km: float | None
    sold_at: date | None
    address: str | None
    neighborhood: str | None
    city: str | None
    same_condo: bool


@dataclass(frozen=True)
class Comparables:
    sold: tuple[SoldComparable, ...]
    available: tuple[SoldComparable, ...]
    same_condo: tuple[SoldComparable, ...]
    on_market_m2: float | None
    off_market_m2: float | None
    days_until_deal: int | None


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _int(value: Any) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def _post(url: str, body: dict, request_fn: Callable[..., Any]) -> dict:
    resposta = request_fn(
        "POST",
        url,
        headers=dict(HEADERS),
        json_body=body,
        timeout=30,
        min_interval=MIN_INTERVAL_SECONDS,
    )
    status = int(getattr(resposta, "status_code", 0) or 0)
    if status in BLOCKED_STATUS:
        raise PortalBlocked(f"http_{status}")
    if status >= 400:
        raise RuntimeError(f"http_{status}")
    payload = resposta.json()
    if not isinstance(payload, dict):
        raise RuntimeError("invalid_payload")
    return payload


def _estimate_body(entrada: EstimateInput) -> dict:
    return {
        "bathroomCount": entrada.bathroom_count,
        "bedroomCount": entrada.bedroom_count,
        "condominiumPerMonth": entrada.condominium_per_month,
        "iptuPerYear": entrada.iptu_per_year,
        "suitesCount": entrada.suites_count,
        "parkingSlots": entrada.parking_slots,
        "address": entrada.address,
        "neighborhood": entrada.neighborhood,
        "city": entrada.city,
        "state": entrada.state,
        "country": entrada.country,
        "latitude": entrada.latitude,
        "longitude": entrada.longitude,
        "businessContext": "SALE",
        "houseType": entrada.house_type,
        "floor": entrada.floor,
        "totalArea": entrada.total_area,
        "addressNumber": entrada.address_number,
    }


def _percentis(bruto: Any) -> dict[int, float]:
    """Os decis que o portal de fato calculou.

    Ele devolve `0` nas casas que não calcula — 20, 40, 60 e 80 vieram zerados
    em todas as consultas medidas. Guardar zero seria guardar mentira.
    """
    if not isinstance(bruto, dict):
        return {}
    encontrados: dict[int, float] = {}
    for chave, valor in bruto.items():
        numero, preco = _int(chave), _float(valor)
        if numero is not None and preco is not None:
            encontrados[numero] = preco
    return encontrados


def fetch_estimate(
    entrada: EstimateInput, *, request_fn: Callable[..., Any] = default_request
) -> Estimate:
    """A estimativa do modelo para este endereço, ou `QprecoUnavailable`."""
    payload = _post(URL_ESTIMATE, _estimate_body(entrada), request_fn)
    preco = _float(payload.get("suggestedPrice"))
    if preco is None:
        raise QprecoUnavailable(
            "o portal não calculou preço — confira a coordenada antes de "
            "concluir que o imóvel é atípico"
        )
    return Estimate(
        suggested_price=preco,
        lower_bound=_float(payload.get("suggestedLowerBoundPrice")),
        upper_bound=_float(payload.get("suggestedUpperBoundPrice")),
        limit_lower=_float(payload.get("lowerBoundLimit")),
        limit_upper=_float(payload.get("upperBoundLimit")),
        certainty=(payload.get("predictionCertainty") or None),
        percentiles=_percentis(payload.get("percentiles")),
    )


def _comparable(row: Any) -> SoldComparable | None:
    if not isinstance(row, dict):
        return None
    preco = _float(row.get("price"))
    if preco is None:
        return None
    quando = str(row.get("lastTimeOnMarket") or "")[:10]
    try:
        vendido_em = date.fromisoformat(quando) if quando else None
    except ValueError:
        vendido_em = None
    distancia = _float(row.get("distance"))
    return SoldComparable(
        house_id=_int(row.get("houseId")),
        price=preco,
        price_m2=_float(row.get("priceM2")),
        total_area=_float(row.get("totalArea")),
        bedroom_count=_int(row.get("bedroomCount")),
        parking_slots=_int(row.get("parkingSlots")),
        distance_km=distancia,
        sold_at=vendido_em,
        address=row.get("address"),
        neighborhood=row.get("neighborhood"),
        city=row.get("city"),
        same_condo=bool(row.get("sameCondo")),
    )


def _lista(payload: dict, chave: str) -> tuple[SoldComparable, ...]:
    linhas = payload.get(chave)
    if not isinstance(linhas, list):
        return ()
    return tuple(c for c in (_comparable(row) for row in linhas) if c is not None)


def fetch_comparables(
    entrada: EstimateInput,
    estimate: Estimate,
    *,
    request_fn: Callable[..., Any] = default_request,
) -> Comparables:
    """Os comparáveis do entorno, na mesma faixa de preço da estimativa.

    A faixa filtra os comparáveis do lado do portal; mandar a da própria
    estimativa é o que a tela deles faz, e é o que mantém a resposta comparável
    com a que o dono veria no site.
    """
    body = {
        "percentile10": estimate.limit_lower or estimate.suggested_price * 0.5,
        "percentile90": estimate.limit_upper or estimate.suggested_price * 1.5,
        "latitude": entrada.latitude,
        "longitude": entrada.longitude,
        "condominiumPerMonth": entrada.condominium_per_month,
        "bathroomCount": entrada.bathroom_count,
        "bedroomCount": entrada.bedroom_count,
        "totalArea": entrada.total_area,
        "houseType": entrada.house_type,
        "city": entrada.city,
        "address": entrada.address,
        "number": entrada.address_number,
        "businessContext": "SALE",
    }
    payload = _post(URL_SIMILARES, body, request_fn)
    resumo = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    dias = _float(resumo.get("daysOnMarketUntilDealAverage"))
    return Comparables(
        sold=_lista(payload, "unavailableSimilarHouses"),
        available=_lista(payload, "availableSimilarHouses"),
        same_condo=_lista(payload, "negotiatedInTheSameCondo"),
        on_market_m2=_float(resumo.get("onMarketPriceBySquareMeter")),
        off_market_m2=_float(resumo.get("offMarketPriceBySquareMeter")),
        days_until_deal=int(dias) if dias is not None else None,
    )
