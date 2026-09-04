"""O diretório de condomínios do QuintoAndar: o número da rua que o anúncio não dá.

A limitação que mais custou à escada de referência é que Loft e QuintoAndar
publicam a rua e não publicam o número. Sem número o anúncio nunca alcança o
tier de endereço exato, onde o erro medido é 5-13%, e cai no de rua ou de
bairro, onde é 14-25%.

O portal publica esse número em outro lugar: uma página por prédio, indexada em
`sitemap-v3-condos-part-*.xml` e liberada pelo `robots.txt`. São 19.117 páginas
de Belo Horizonte. Medido em 59 delas sorteadas do sitemap:

    trazem o número                                   59/59
    casam com o cadastro da PBH por rua+numero        49/59  (83%)
    distancia do ponto ao lote do cadastro            p50 8 m, p90 24 m
    distancia do ponto ao anuncio do proprio portal   p50 1 m, max 27 m

O payload vem no `__NEXT_DATA__` da página, sob `condoInfo`, e responde a um GET
comum — sem sessão, sem cookie e sem navegador. Este módulo é só o parser; o
I/O, o ritmo e a escolha de quais páginas baixar estão em
`app/services/condo_sync.py`.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.slugs import address_key, street_key

SOURCE = "quintoandar"
SITEMAP_INDEX = "https://www.quintoandar.com.br/sitemap-v3.xml"

_CONDO_PART = re.compile(r"sitemap-v3-condos-part-\d+\.xml$")
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_URL_BLOCK = re.compile(r"<url\b.*?</url>", re.I | re.S)
_LASTMOD = re.compile(r"<lastmod>\s*(\d{4}-\d{2}-\d{2})", re.I)
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.I | re.S)
# O slug termina em `-{hashId}`, dez caracteres alfanuméricos.
_SLUG_TAIL = re.compile(r"-([a-z0-9]{10})$")


@dataclass(frozen=True)
class CondoRow:
    """Um prédio como o portal o publica."""

    source: str
    external_id: str
    slug: str | None
    url: str
    city: str
    street: str | None
    street_number: str | None
    street_key: str | None
    number_key: str | None
    postal_code: str | None
    neighborhood: str | None
    lat: float | None
    lon: float | None
    min_area: float | None
    max_area: float | None
    min_bedrooms: int | None
    max_bedrooms: int | None
    installations: list[str] | None
    doorman: str | None
    source_lastmod: date | None


def sitemap_parts(index_xml: str) -> list[str]:
    """As partições de condomínio do índice de sitemaps, na ordem em que vêm.

    O índice mistura buscas, regiões e páginas de cidade; só esta família tem
    uma página por prédio.
    """
    return [url for url in _LOC.findall(index_xml) if _CONDO_PART.search(url)]


def condo_entries(sitemap_xml: str, city_slug: str) -> list[tuple[str, date | None]]:
    """(URL, data da última alteração) das páginas daquela cidade.

    O sitemap é nacional — 179.572 páginas, das quais 19.117 são de Belo
    Horizonte. A cidade está no fim do slug, antes do hash, então filtrar por
    texto é exato e evita abrir cada página para descobrir que ela é de outro
    estado.
    """
    encontrados: list[tuple[str, date | None]] = []
    marca = f"-{city_slug}-"
    for bloco in _URL_BLOCK.findall(sitemap_xml):
        achado = _LOC.search(bloco)
        if achado is None or marca not in achado.group(1):
            continue
        quando = _LASTMOD.search(bloco)
        encontrados.append(
            (achado.group(1), date.fromisoformat(quando.group(1)) if quando else None)
        )
    return encontrados


def slug_neighborhood(url: str, city_slug: str) -> str | None:
    """O bairro que o slug declara, que é o que dá para filtrar antes de baixar.

    Metade dos slugs começa pela rua e a outra metade pelo nome do prédio, mas
    todos terminam em `-{bairro}-{cidade}-{hash}`. O bairro é o que permite
    gastar o orçamento de uma execução onde existe anúncio sem prédio
    resolvido, em vez de baixar dezessete gigabytes de páginas.
    """
    slug = _SLUG_TAIL.sub("", url.rstrip("/").rsplit("/", 1)[-1])
    marca = f"-{city_slug}"
    if not slug.endswith(marca):
        return None
    return slug[: -len(marca)].rsplit("-", 1)[-1] or None


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _condo_info(payload: Any, profundidade: int = 0) -> dict | None:
    """`condoInfo` mora sob `props.pageProps`, mas o portal já moveu a chave de
    lugar entre versões do bundle — procurar custa menos do que reagir a isso
    quando a coleta inteira começa a devolver vazio."""
    if profundidade > 8 or not isinstance(payload, dict):
        return None
    achado = payload.get("condoInfo")
    if isinstance(achado, dict):
        return achado
    for valor in payload.values():
        if isinstance(valor, dict):
            encontrado = _condo_info(valor, profundidade + 1)
            if encontrado is not None:
                return encontrado
    return None


def _installations(features: dict) -> list[str] | None:
    """Só o que o prédio tem.

    O portal publica `"NAO"` como resposta, e não como ausência. Guardar as
    duas encheria a coluna de ruído e faria a contagem de comodidades dizer o
    contrário do que diz.
    """
    itens = features.get("installations")
    if not isinstance(itens, list):
        return None
    presentes = sorted(
        chave
        for item in itens
        if isinstance(item, dict)
        and str(item.get("value", "")).strip().upper() == "SIM"
        and (chave := _clean(item.get("key")))
    )
    return presentes or None


def parse_condo_page(
    html: str, url: str, *, city: str, lastmod: date | None = None
) -> CondoRow | None:
    """Lê uma página de condomínio, ou devolve None quando ela não serve.

    Sem número da rua a página não responde à pergunta que a fez ser baixada, e
    guardá-la só encheria a tabela — então ela é descartada aqui, e não depois.
    """
    achado = _NEXT_DATA.search(html)
    if achado is None:
        return None
    try:
        payload = json.loads(achado.group(1))
    except json.JSONDecodeError:
        return None
    info = _condo_info(payload)
    if info is None:
        return None

    rua, numero = _clean(info.get("address")), _clean(info.get("number"))
    chave_rua, chave_numero = street_key(rua), address_key(numero)
    if not chave_rua or not chave_numero:
        return None

    features = info.get("features") if isinstance(info.get("features"), dict) else {}
    lat, lon = _float(info.get("lat")), _float(info.get("lng"))
    return CondoRow(
        source=SOURCE,
        external_id=str(info.get("hashId") or "").strip(),
        slug=_clean(info.get("slug")),
        url=url,
        city=city,
        street=rua,
        street_number=numero,
        street_key=chave_rua,
        number_key=chave_numero,
        postal_code=_clean(info.get("zipCode")),
        neighborhood=_clean(info.get("neighborhood")),
        # Seis casas é a precisão que `registry_addresses` já guarda, e basta
        # para distinguir lotes vizinhos; o portal devolve o float inteiro.
        lat=round(lat, 6) if lat is not None else None,
        lon=round(lon, 6) if lon is not None else None,
        # A faixa de área das unidades que o portal conhece naquele prédio —
        # outra leitura do formato, em área anunciada, ao lado da do cadastro
        # em área construída.
        min_area=_float(info.get("minArea")),
        max_area=_float(info.get("maxArea")),
        min_bedrooms=_int(info.get("minBedrooms")),
        max_bedrooms=_int(info.get("maxBedrooms")),
        installations=_installations(features),
        doorman=_clean(features.get("doorman")),
        source_lastmod=lastmod,
    )
