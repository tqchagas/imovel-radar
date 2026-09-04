"""Avalia um imóvel de leilão: duas leituras do portal, mais o ITBI onde houver.

A coordenada é o campo mais sensível de todos — medido, seis metros moveram a
estimativa em 18,4%, de forma determinística. Por isso ela nunca é
geocodificada em silêncio: em Belo Horizonte o serviço *sugere* um ponto a
partir de rua+número, e quem grava é o dono, que confere. Fora dali, ele cola.

A ordem da sugestão não é arbitrária: o diretório de condomínios publica o
ponto que o próprio QuintoAndar usa para o prédio, e é contra ele que o modelo
foi indexado; o lote do cadastro da prefeitura é a segunda melhor coisa, e fica
a cerca de oito metros dali.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_client import PortalBlocked
from app.core.http_client import request as default_request
from app.domain.appraisal import avaliar
from app.domain.opportunities import (
    ListingInput,
    SaleIndex,
    build_calibration,
    compute_opportunity,
)
from app.domain.slugs import address_key, street_key
from app.models.auction_property import AuctionAppraisal, AuctionProperty
from app.models.portal_building import PortalBuilding
from app.models.registry_address import RegistryAddress
from app.pricing.qpreco_calculadora import (
    EstimateInput,
    QprecoUnavailable,
    fetch_comparables,
    fetch_estimate,
)
from app.services.opportunities import (
    _active_listings,
    _listing_input,
    fetch_portal_buildings,
    fetch_reference_sales,
    fetch_registry_buildings,
    latest_reference_date,
)
from app.domain.market_stats import shift_months

TTL_DIAS = 30

FONTE_PORTAL = "portal"
FONTE_CADASTRO = "cadastro"
FONTE_MANUAL = "manual"

# O rótulo que a tela mostra para cada fonte, e o quanto ela merece confiança.
FONTE_LABEL = {
    FONTE_PORTAL: "ponto do prédio no QuintoAndar",
    FONTE_CADASTRO: "lote do cadastro da prefeitura",
    FONTE_MANUAL: "informada por você",
}


def _float(value) -> float | None:
    return float(value) if value is not None else None


def sugerir_coordenada(
    db: Session, *, city: str, street: str, number: str | None
) -> tuple[float, float, str] | None:
    """Um ponto para o dono confirmar, ou None quando não há base para chutar.

    Só Belo Horizonte tem o diretório e o cadastro carregados. Em qualquer
    outra cidade a resposta honesta é não ter resposta — inventar uma
    coordenada aqui é o modo de falha que este desenho existe para evitar.
    """
    chave_rua, chave_numero = street_key(street), address_key(number)
    if not chave_rua or not chave_numero or address_key(city) != "belo_horizonte":
        return None

    predio = db.execute(
        select(PortalBuilding.lat, PortalBuilding.lon)
        .where(PortalBuilding.city == "belo_horizonte")
        .where(PortalBuilding.street_key == chave_rua)
        .where(PortalBuilding.number_key == chave_numero)
        .where(PortalBuilding.lat.is_not(None))
    ).first()
    if predio:
        return float(predio[0]), float(predio[1]), FONTE_PORTAL

    lote = db.execute(
        select(RegistryAddress.lat, RegistryAddress.lon)
        .where(RegistryAddress.city == "belo_horizonte")
        .where(RegistryAddress.street_key == chave_rua)
        .where(RegistryAddress.number_key == chave_numero)
        .where(RegistryAddress.lat.is_not(None))
    ).first()
    if lote:
        return float(lote[0]), float(lote[1]), FONTE_CADASTRO
    return None


def _entrada(imovel: AuctionProperty) -> EstimateInput:
    numero = (imovel.address_number or "").strip()
    return EstimateInput(
        address=imovel.address,
        address_number=int(numero) if numero.isdigit() else None,
        neighborhood=imovel.neighborhood,
        city=imovel.city,
        state=imovel.state,
        latitude=float(imovel.latitude),
        longitude=float(imovel.longitude),
        house_type=imovel.house_type or "APARTMENT",
        total_area=float(imovel.total_area),
        bedroom_count=imovel.bedroom_count or 2,
        bathroom_count=imovel.bathroom_count or 1,
        suites_count=imovel.suites_count or 0,
        parking_slots=imovel.parking_slots or 0,
        floor=imovel.floor,
        condominium_per_month=_float(imovel.condominium_per_month) or 0,
        iptu_per_year=_float(imovel.iptu_per_year) or 0,
    )


def conferencia_itbi(db: Session, imovel: AuctionProperty) -> tuple[float, str, int] | None:
    """A escada de referência de ITBI no endereço, quando a cidade tem base.

    É uma terceira leitura, independente das duas do portal, e a única baseada
    em quitação de cartório. Fora de Belo Horizonte não existe e a ausência
    dela não muda mais nada.
    """
    cidade = address_key(imovel.city)
    if not cidade:
        return None
    dia = latest_reference_date(db, cidade)
    if dia is None:
        return None

    vendas = fetch_reference_sales(db, cidade, shift_months(dia, 24), dia)
    if not vendas:
        return None

    entrada = ListingInput(
        source="leilao",
        listing_id=str(imovel.id),
        tipo_imovel="APARTAMENTO" if imovel.house_type == "APARTMENT" else "CASA",
        area_util_m2=float(imovel.total_area),
        # O preço não é conhecido; a escada só precisa dele para o desconto, e
        # aqui interessa apenas o preço estimado.
        preco_total=1.0,
        bairro=imovel.neighborhood,
        rua=imovel.address,
        numero=imovel.address_number,
    )
    index = SaleIndex.build(vendas, dia)

    # A calibração precisa dos anúncios reais da cidade, e não deste imóvel: ela
    # exige um piso de quinze anúncios por escopo, e um imóvel sintético sozinho
    # nunca o alcança — `factor()` devolveria None e a leitura de ITBI sumiria
    # em silêncio, que foi exatamente o que aconteceu na primeira versão.
    predios = fetch_registry_buildings(db, cidade)
    portal = fetch_portal_buildings(db, cidade)
    anuncios = [
        _listing_input(linha, None, predios, portal)
        for linha in _active_listings(db, cidade, None)
    ]
    if not anuncios:
        return None
    calibracao = build_calibration(anuncios, index)
    oportunidade = compute_opportunity(entrada, index, dia, calibracao)
    if oportunidade is None or oportunidade.preco_estimado_itbi <= 0:
        # Sem fator medido para o escopo nada é emitido — é a mesma disciplina
        # do produto de oportunidades, e não se cai para 1,0.
        return None
    return (
        float(oportunidade.preco_estimado_itbi),
        oportunidade.tipo_referencia,
        oportunidade.amostra_count,
    )


def ultima_avaliacao(db: Session, imovel: AuctionProperty) -> AuctionAppraisal | None:
    return db.execute(
        select(AuctionAppraisal)
        .where(AuctionAppraisal.auction_property_id == imovel.id)
        .order_by(AuctionAppraisal.consultado_em.desc())
        .limit(1)
    ).scalars().first()


def _fresca(avaliacao: AuctionAppraisal | None, agora: datetime) -> bool:
    if avaliacao is None or avaliacao.consultado_em is None or avaliacao.preco_qpreco is None:
        return False
    quando = avaliacao.consultado_em
    if quando.tzinfo is not None:
        quando = quando.replace(tzinfo=None)
    return (agora - quando) < timedelta(days=TTL_DIAS)


def avaliar_imovel(
    db: Session,
    imovel: AuctionProperty,
    *,
    force: bool = False,
    request_fn: Callable[..., Any] = default_request,
    now: datetime | None = None,
) -> AuctionAppraisal:
    """Consulta o portal e grava a leitura, respeitando o TTL."""
    agora = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    anterior = ultima_avaliacao(db, imovel)
    if not force and _fresca(anterior, agora):
        return anterior

    entrada = _entrada(imovel)
    registro = AuctionAppraisal(auction_property_id=imovel.id, consultado_em=agora)

    try:
        estimativa = fetch_estimate(entrada, request_fn=request_fn)
    except (QprecoUnavailable, PortalBlocked, RuntimeError) as erro:
        # Guardar a falha é o que evita reconsultar em loop e o que deixa a
        # tela dizer o que houve, em vez de mostrar uma linha vazia.
        registro.erro = str(erro)[:300]
        db.add(registro)
        db.commit()
        return registro

    try:
        comparaveis = fetch_comparables(entrada, estimativa, request_fn=request_fn)
        vendidos = comparaveis.sold
    except (PortalBlocked, RuntimeError) as erro:
        vendidos = ()
        registro.erro = f"comparáveis indisponíveis: {erro}"[:300]

    leitura = avaliar(
        estimativa,
        vendidos,
        area=float(imovel.total_area),
        quartos=imovel.bedroom_count or 2,
    )

    registro.preco_qpreco = leitura.preco_qpreco
    registro.preco_rapido = estimativa.lower_bound
    registro.preco_devagar = estimativa.upper_bound
    registro.limite_inferior = estimativa.limit_lower
    registro.limite_superior = estimativa.limit_upper
    registro.certeza = leitura.certeza
    registro.preco_vendidos = leitura.preco_vendidos
    registro.comparaveis_usados = leitura.comparaveis_usados
    registro.divergencia_pct = leitura.divergencia_pct
    registro.atipico = leitura.atipico
    registro.comparaveis_json = [
        {**asdict(c), "sold_at": c.sold_at.isoformat() if c.sold_at else None}
        for c in vendidos
    ] or None

    itbi = conferencia_itbi(db, imovel)
    if itbi is not None:
        registro.preco_itbi, registro.itbi_tier, registro.itbi_amostra = itbi

    db.add(registro)
    db.commit()
    db.refresh(registro)
    return registro
