"""Duas leituras de valor para o mesmo imóvel, e o que a discordância diz.

A Calculadora QPreço devolve uma estimativa do modelo e, na mesma consulta, os
comparáveis que o portal reporta como já vendidos. São duas leituras
independentes: uma é o que um modelo acha, a outra é o que gente pagou.

Nenhuma das duas é arbitrada como certa. O que se guarda é a divergência entre
elas — quando concordam, a leitura é confiável; quando discordam, o imóvel é
atípico e pede olho humano. É a mesma forma do `min(nota_itbi, nota_qpreco)`
que a nota de oportunidade já usa: a segunda referência serve para desconfiar,
não para inflar.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Sequence

from app.pricing.qpreco_calculadora import Estimate, SoldComparable

# A mesma janela da escada de referência: ela existe para não comparar
# quarto-e-sala com cobertura.
TOLERANCIA_AREA = 0.20
DISTANCIA_MAX_KM = 1.0
# Abaixo disso a mediana é o próprio ruído.
MIN_COMPARAVEIS = 3
# Acima disso as duas leituras discordam o bastante para pedir olho humano.
DIVERGENCIA_ALERTA = 0.15


@dataclass(frozen=True)
class Appraisal:
    preco_qpreco: float
    preco_vendidos: float | None
    divergencia_pct: float | None
    atipico: bool
    certeza: str | None
    comparaveis_usados: int


def comparaveis_uteis(
    vendidos: Sequence[SoldComparable], *, area: float, quartos: int
) -> tuple[SoldComparable, ...]:
    """Os vendidos que de fato se parecem com este imóvel.

    `bedroomCount` volta nulo na maioria dos comparáveis — cinco de seis numa
    consulta medida ao vivo. Exigir igualdade esvaziaria a amostra, então nulo
    conta como compatível e é o corte de área que segura. O mesmo vale para a
    distância: o portal já devolveu esta lista como sendo do entorno.
    """
    escolhidos = []
    for c in vendidos:
        if c.total_area is None or c.price_m2 is None:
            continue
        if not area * (1 - TOLERANCIA_AREA) <= c.total_area <= area * (1 + TOLERANCIA_AREA):
            continue
        if c.bedroom_count is not None and c.bedroom_count != quartos:
            continue
        if c.distance_km is not None and c.distance_km > DISTANCIA_MAX_KM:
            continue
        escolhidos.append(c)
    return tuple(escolhidos)


def mediana_dos_vendidos(
    uteis: Sequence[SoldComparable], area: float
) -> float | None:
    """R$/m² mediano dos comparáveis, aplicado à área deste imóvel.

    A mediana é do R$/m², e não do preço: os comparáveis têm áreas diferentes,
    e a mediana dos preços responderia sobre o imóvel mediano da lista em vez
    de sobre este.
    """
    if len(uteis) < MIN_COMPARAVEIS or area <= 0:
        return None
    return median(c.price_m2 for c in uteis) * area


def avaliar(
    estimate: Estimate,
    vendidos: Sequence[SoldComparable],
    *,
    area: float,
    quartos: int,
) -> Appraisal:
    """As duas leituras e a divergência entre elas."""
    uteis = comparaveis_uteis(vendidos, area=area, quartos=quartos)
    preco_vendidos = mediana_dos_vendidos(uteis, area)
    divergencia = (
        (preco_vendidos - estimate.suggested_price) / estimate.suggested_price
        if preco_vendidos is not None and estimate.suggested_price > 0
        else None
    )
    return Appraisal(
        preco_qpreco=estimate.suggested_price,
        preco_vendidos=preco_vendidos,
        divergencia_pct=divergencia,
        atipico=divergencia is not None and abs(divergencia) > DIVERGENCIA_ALERTA,
        certeza=estimate.certainty,
        comparaveis_usados=len(uteis),
    )
