"""Resolve o prédio de um anúncio pela coordenada, quando ele não traz o número.

Loft e QuintoAndar publicam a rua e não publicam o número — 18.585 dos 22.099
anúncios ativos em Belo Horizonte. Sem número, a escada de referência nunca
alcança o tier de endereço exato, onde o erro medido é 5-13%, e cai no de rua
ou de bairro, onde é 14-25%.

A Loft publica coordenada exata do prédio em 99,3% dos anúncios, e o cadastro
imobiliário da prefeitura publica a coordenada do lote de 99,6% dos endereços
de ITBI. Daí sai o número.

Medido contra os 1.530 anúncios do VivaReal que publicam número *e* coordenada
exata, procurando o lote mais próximo dentro da rua que o próprio anúncio
declara:

    raio    resolveu    número certo (dos resolvidos)
     30 m     94,2%              94,2%
     50 m     98,9%              93,9%
     80 m     99,5%              93,6%

Aos 50 m a resolução praticamente satura e o acerto ainda não caiu; passar
disso só compra ambiguidade. Restringir à rua é o que faz a diferença: sem
essa restrição o acerto cai para 90,2% e resolve menos.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from app.domain.geo import haversine_m

MATCH_RADIUS_M = 50.0

# Lado da célula da grade, em graus.
_CELL = 0.0005
# Metros por grau de longitude na latitude de Belo Horizonte — a menor das duas
# dimensões da célula, então usá-la para dimensionar a busca nunca subestima o
# alcance necessário.
_METERS_PER_DEGREE = 104_000.0


@dataclass(frozen=True)
class Building:
    """Um endereço do cadastro, com a coordenada do lote."""

    street_key: str
    number_key: str
    lat: float
    lon: float
    construction_type: str | None = None
    finish_standard: str | None = None
    units_count: int | None = None
    median_unit_area: float | None = None


@dataclass(frozen=True)
class BuildingIndex:
    """Os lotes do cadastro, indexados para a busca por proximidade.

    A busca é por célula de grade, não por varredura: são 31 mil endereços de
    apartamento em Belo Horizonte contra 22 mil anúncios, e o produto dos dois
    não cabe num ciclo de coleta.
    """

    by_cell: Mapping[tuple[str, int, int], list[Building]] = field(default_factory=dict)
    by_address: Mapping[tuple[str, str, str], Building] = field(default_factory=dict)

    @classmethod
    def build(cls, buildings: Iterable[Building]) -> "BuildingIndex":
        by_cell: dict[tuple[str, int, int], list[Building]] = defaultdict(list)
        by_address: dict[tuple[str, str, str], Building] = {}
        for predio in buildings:
            if predio.street_key and predio.number_key and predio.construction_type:
                by_address[(predio.construction_type, predio.street_key, predio.number_key)] = predio
            if predio.lat is None or predio.lon is None or not predio.street_key:
                continue
            by_cell[_cell_of(predio.street_key, predio.lat, predio.lon)].append(predio)
        return cls(dict(by_cell), by_address)

    def resolve(
        self,
        street_key: str | None,
        lat: float | None,
        lon: float | None,
        *,
        radius_m: float = MATCH_RADIUS_M,
    ) -> str | None:
        """Número do lote mais próximo na mesma rua, ou None.

        A rua vem do anúncio e não é adivinhada: um ponto a 40 m pode estar na
        rua de trás, e comparar o anúncio contra o prédio errado de *outra* rua
        é pior do que não resolver nada.
        """
        if not street_key or lat is None or lon is None:
            return None
        melhor: Building | None = None
        distancia = radius_m
        cy, cx = _cell_index(lat, lon)
        # O alcance em células acompanha o raio: com uma vizinhança fixa de uma
        # célula, um raio maior que o lado da célula procuraria num quadrado
        # menor do que ele mesmo e perderia lotes que estão dentro do raio.
        alcance = _cell_span(radius_m)
        for dy in range(-alcance, alcance + 1):
            for dx in range(-alcance, alcance + 1):
                for predio in self.by_cell.get((street_key, cy + dy, cx + dx), ()):
                    d = haversine_m(lat, lon, predio.lat, predio.lon)
                    if d < distancia:
                        melhor, distancia = predio, d
        return melhor.number_key if melhor is not None else None

    def lookup(
        self, construction_type: str | None, street_key: str | None, number_key: str | None
    ) -> Building | None:
        """O endereço do cadastro, quando o número já é conhecido."""
        if not construction_type or not street_key or not number_key:
            return None
        return self.by_address.get((construction_type, street_key, number_key))


def _cell_span(radius_m: float) -> int:
    """Quantas células de cada lado a busca precisa varrer para cobrir o raio."""
    return max(1, math.ceil(radius_m / (_CELL * _METERS_PER_DEGREE)))


def _cell_index(lat: float, lon: float) -> tuple[int, int]:
    return round(lat / _CELL), round(lon / _CELL)


def _cell_of(street_key: str, lat: float, lon: float) -> tuple[str, int, int]:
    cy, cx = _cell_index(lat, lon)
    return street_key, cy, cx


def buildings_from_rows(rows: Sequence) -> list[Building]:
    """Converte linhas de `registry_addresses` em `Building`."""
    return [
        Building(
            street_key=row.street_key,
            number_key=row.number_key,
            lat=float(row.lat),
            lon=float(row.lon),
            construction_type=row.construction_type,
            finish_standard=row.finish_standard,
            units_count=row.units_count,
            median_unit_area=float(row.median_unit_area) if row.median_unit_area else None,
        )
        for row in rows
        if row.lat is not None and row.lon is not None
    ]
