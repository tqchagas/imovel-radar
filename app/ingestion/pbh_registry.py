"""Cadastro imobiliário de Belo Horizonte: endereço, tipo e coordenada do lote.

A prefeitura publica no CKAN um CSV por regional administrativa, mensal, com
uma linha por economia tributária — a unidade autônoma. Cada linha traz o
logradouro abreviado no mesmo padrão do ITBI, o número do imóvel, o tipo
construtivo, o padrão de acabamento, a área de construção e a geometria do lote
em UTM SIRGAS2000.

O que se guarda daqui é o endereço agregado, não a economia: a escada de
referência pergunta "quais vendas aconteceram neste prédio", e é nessa
granularidade que a coordenada resolve o anúncio que publica rua e ponto mas
não publica número.

Fonte: https://dados.pbh.gov.br — busque "cadastro imobiliário". As dez
regionais são conjuntos separados; `resource_urls` acha a extração mais recente
de cada uma pela API do CKAN.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from statistics import median, quantiles
from typing import IO

from app.domain.geo import polygon_centroid, utm_to_latlon
from app.domain.slugs import address_key, street_key

CITY = "belo_horizonte"
CKAN_SEARCH = "https://dados.pbh.gov.br/api/3/action/package_search"
CKAN_QUERY = "cadastro imobiliario"

# O cadastro escreve o tipo construtivo por extenso; o ITBI usa a sigla de duas
# letras, e é ela que a escada de referência indexa. Só o que a escada compara
# entra: apartamento e casa residenciais.
CONSTRUCTION_TYPES = {
    "APARTAMENTO": "AP",
    "CASA": "CA",
}

# O CSV vem com ponto e vírgula e um polígono por linha que passa folgadamente
# do limite padrão de campo do módulo csv. (O BOM é tratado por quem abre o
# arquivo, com encoding "utf-8-sig".)
_DELIMITER = ";"
FIELD_SIZE_LIMIT = 10_000_000

_RESOURCE_NAME = re.compile(r"^(\d{8})_regional_([a-z_\-]+)_cadastro_imobiliario", re.I)


@dataclass(frozen=True)
class RegistryRow:
    """Um endereço do cadastro, já agregado a partir das suas economias."""

    city: str
    street: str
    street_number: str
    street_key: str
    number_key: str
    construction_type: str
    occupation_type: str | None
    postal_code: str | None
    finish_standard: str | None
    units_count: int
    median_unit_area: float | None
    unit_area_dispersion: float | None
    unit_area_profile: list[float] | None
    lat: float | None
    lon: float | None
    source_date: date | None


def _clean(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _float(value: str | None) -> float | None:
    raw = _clean(value)
    if raw is None:
        return None
    try:
        number = float(raw.replace(",", "."))
    except ValueError:
        return None
    return number if number > 0 else None


def resource_urls(payload: dict) -> dict[str, tuple[str, str]]:
    """Extração mais recente de cada regional, a partir de um `package_search`.

    A prefeitura mantém os meses anteriores publicados lado a lado no mesmo
    conjunto, então a escolha é pela data no nome do recurso, não pela ordem.
    """
    encontrados: dict[str, tuple[str, str]] = {}
    for pacote in payload.get("result", {}).get("results", []):
        if "cadastro-imobiliario" not in (pacote.get("name") or ""):
            continue
        for recurso in pacote.get("resources", []):
            if (recurso.get("format") or "").upper() != "CSV":
                continue
            achado = _RESOURCE_NAME.match((recurso.get("name") or "").strip())
            if not achado:
                continue
            data, regional = achado.group(1), achado.group(2).lower().strip("_-")
            atual = encontrados.get(regional)
            if atual is None or data > atual[0]:
                encontrados[regional] = (data, recurso["url"])
    return encontrados


def _source_date(stamp: str | None) -> date | None:
    if not stamp or len(stamp) != 8 or not stamp.isdigit():
        return None
    return date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]))


def parse_file(
    handle: IO[str], *, city: str = CITY, source_stamp: str | None = None
) -> Iterator[RegistryRow]:
    """Lê um CSV de regional e devolve um `RegistryRow` por endereço."""
    csv.field_size_limit(FIELD_SIZE_LIMIT)
    reader = csv.DictReader(handle, delimiter=_DELIMITER)
    yield from aggregate(reader, city=city, source_stamp=source_stamp)


def aggregate(
    rows: Iterable[dict], *, city: str = CITY, source_stamp: str | None = None
) -> Iterator[RegistryRow]:
    """Agrupa as economias por endereço e tipo construtivo.

    A coordenada do endereço é a mediana das coordenadas dos lotes que ele
    reúne, não a média: um lote com geometria errada desloca a média e não move
    a mediana, e o cadastro tem alguns.
    """
    grupos: dict[tuple, dict] = defaultdict(
        lambda: {
            "lats": [],
            "lons": [],
            "areas": [],
            "padroes": defaultdict(int),
            "ocupacoes": defaultdict(int),
        }
    )
    identidade: dict[tuple, tuple[str, str, str | None]] = {}

    for row in rows:
        construcao = CONSTRUCTION_TYPES.get((row.get("TIPO_CONSTRUTIVO") or "").strip().upper())
        if construcao is None:
            continue
        logradouro = " ".join(
            parte
            for parte in ((row.get("TIPO_LOGRADOURO") or "").strip(), (row.get("NOME_LOGRADOURO") or "").strip())
            if parte
        )
        numero = (row.get("NUMERO_IMOVEL") or "").strip()
        rua_chave = street_key(logradouro)
        numero_chave = address_key(numero)
        if not rua_chave or not numero_chave:
            continue

        chave = (city, rua_chave, numero_chave, construcao)
        identidade.setdefault(chave, (logradouro, numero, _clean(row.get("CEP"))))
        grupo = grupos[chave]

        centro = polygon_centroid(row.get("GEOMETRIA"))
        if centro is not None:
            lat, lon = utm_to_latlon(*centro)
            grupo["lats"].append(lat)
            grupo["lons"].append(lon)
        area = _float(row.get("AREA_CONSTRUCAO"))
        if area is not None:
            grupo["areas"].append(area)
        padrao = _clean(row.get("PADRAO_ACABAMENTO"))
        if padrao:
            grupo["padroes"][padrao] += 1
        ocupacao = _clean(row.get("TIPO_OCUPACAO"))
        if ocupacao:
            grupo["ocupacoes"][ocupacao] += 1

    fonte = _source_date(source_stamp)
    for chave, grupo in grupos.items():
        cidade, rua_chave, numero_chave, construcao = chave
        logradouro, numero, cep = identidade[chave]
        yield RegistryRow(
            city=cidade,
            street=logradouro,
            street_number=numero,
            street_key=rua_chave,
            number_key=numero_chave,
            construction_type=construcao,
            occupation_type=_predominante(grupo["ocupacoes"]),
            postal_code=cep,
            finish_standard=_predominante(grupo["padroes"]),
            # Quantas unidades daquele tipo o endereço tem. É a resposta a
            # "prédio de 8 apartamentos ou de 120", que muda o quanto uma
            # amostra de duas vendas fala pelo conjunto.
            units_count=len(grupo["areas"]) or len(grupo["lats"]),
            median_unit_area=round(median(grupo["areas"]), 2) if grupo["areas"] else None,
            unit_area_dispersion=_dispersion(grupo["areas"]),
            unit_area_profile=_profile(grupo["areas"]),
            lat=round(median(grupo["lats"]), 6) if grupo["lats"] else None,
            lon=round(median(grupo["lons"]), 6) if grupo["lons"] else None,
            source_date=fonte,
        )


def _dispersion(areas: list[float]) -> float | None:
    """Quanto as unidades do endereço discordam entre si em área.

    Espalhamento interquartil sobre a mediana, a mesma forma que a escada de
    referência usa para medir a discordância de uma amostra de ITBI. Abaixo de
    quatro unidades não há quartil a medir, e um prédio de três apartamentos
    não é evidência de nada — devolve None, e quem lê decide.
    """
    if len(areas) < 4:
        return None
    meio = median(areas)
    if meio <= 0:
        return None
    inferior, _, superior = quantiles(sorted(areas), n=4)
    return round((superior - inferior) / meio, 4)


def _profile(areas: list[float]) -> list[float] | None:
    """O formato do prédio: onze decis das áreas das suas unidades.

    A mediana diz o tamanho do apartamento típico e não diz que o prédio tem
    coberturas. Onde as unidades discordam entre si — 24% dos prédios, medido
    pela dispersão interquartil — é o posto do anúncio dentro desta lista que
    diz qual unidade ele é; a mediana sozinha comparava a cobertura com o
    quarto e sala.

    Onze números cabem em qualquer prédio e bastam para resolver o posto.
    Abaixo de quatro unidades vale o mesmo piso da dispersão: sem quartil não
    há formato a descrever, devolve None e quem lê decide.
    """
    if len(areas) < 4:
        return None
    ordenadas = sorted(areas)
    ultimo = len(ordenadas) - 1
    return [round(ordenadas[round(decil * ultimo / 10)], 2) for decil in range(11)]


def _predominante(contagem: dict[str, int]) -> str | None:
    """O valor mais comum entre as economias, ou None quando não há nenhum."""
    if not contagem:
        return None
    return max(contagem.items(), key=lambda item: (item[1], item[0]))[0]
