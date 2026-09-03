"""Coordenadas: UTM para geográfica, distância, e o centro de um polígono.

A prefeitura publica o cadastro imobiliário com a geometria do lote em UTM
SIRGAS2000 — em Belo Horizonte, fuso 23S. Os anúncios chegam em latitude e
longitude. Para casar um anúncio com o lote que ele ocupa, as duas pontas
precisam estar no mesmo sistema.

A conversão é a série inversa de Krüger, fechada e determinística. Ela entra
aqui à mão em vez de vir do `pyproj` porque o projeto inteiro tem onze
dependências e nenhuma binária pesada, e porque a precisão que a série entrega
— submétrica dentro do fuso — é uma ordem de grandeza melhor do que a que este
uso pede: distinguir um prédio do vizinho, algo em torno de 20 m.

SIRGAS2000 usa o elipsoide GRS80. WGS84 usa o WGS84, que difere do GRS80 no
achatamento a partir da décima primeira casa decimal — algo abaixo de 1 mm no
raio terrestre. Tratá-los como o mesmo datum é o que todo mundo faz, e aqui
não chega perto de importar.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# GRS80, o elipsoide do SIRGAS2000.
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)

# Parâmetros do UTM, iguais em qualquer fuso.
_K0 = 0.9996
_FALSE_EASTING = 500000.0
# Só no hemisfério sul: o equador recebe 10.000 km para o northing não negativar.
_FALSE_NORTHING_SOUTH = 10000000.0

# Belo Horizonte inteira cabe no fuso 23, meridiano central -45.
BH_UTM_ZONE = 23
BH_UTM_SOUTH = True

_RAIO_TERRA_M = 6371008.8


def utm_central_meridian(zone: int) -> float:
    return (zone - 1) * 6 - 180 + 3


def utm_to_latlon(
    easting: float, northing: float, zone: int = BH_UTM_ZONE, south: bool = BH_UTM_SOUTH
) -> tuple[float, float]:
    """Converte UTM SIRGAS2000/GRS80 para latitude e longitude em graus."""
    y = northing - (_FALSE_NORTHING_SOUTH if south else 0.0)
    x = easting - _FALSE_EASTING

    m = y / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256))

    e1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
    # Latitude do pé da perpendicular: a série que desfaz o arco meridiano.
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )

    sin_phi1, cos_phi1, tan_phi1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = _EP2 * cos_phi1**2
    t1 = tan_phi1**2
    n1 = _A / math.sqrt(1 - _E2 * sin_phi1**2)
    r1 = _A * (1 - _E2) / (1 - _E2 * sin_phi1**2) ** 1.5
    d = x / (n1 * _K0)

    lat = phi1 - (n1 * tan_phi1 / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * _EP2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * _EP2 - 3 * c1**2) * d**6 / 720
    )
    lon = (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * _EP2 + 24 * t1**2) * d**5 / 120
    ) / cos_phi1

    return math.degrees(lat), utm_central_meridian(zone) + math.degrees(lon)


_COORD_PAIR = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")


def polygon_centroid(wkt: str | None) -> tuple[float, float] | None:
    """Centro do polígono WKT, na mesma unidade em que ele veio.

    A média dos vértices, não o centroide de área. O lote urbano é convexo e
    curto o bastante para as duas coincidirem dentro de poucos metros, e a
    média não precisa saber lidar com anel interno, orientação ou multipolígono
    — formas que aparecem no cadastro e quebrariam a fórmula de área.
    """
    if not wkt:
        return None
    pontos = _COORD_PAIR.findall(wkt)
    if not pontos:
        return None
    # O WKT fecha o anel repetindo o primeiro vértice; contá-lo duas vezes
    # inclina o centro para aquele canto.
    if len(pontos) > 1 and pontos[0] == pontos[-1]:
        pontos = pontos[:-1]
    if not pontos:
        return None
    xs = [float(px) for px, _ in pontos]
    ys = [float(py) for _, py in pontos]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em metros entre dois pontos geográficos."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _RAIO_TERRA_M * math.asin(math.sqrt(h))


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float
