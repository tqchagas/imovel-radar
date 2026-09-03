"""Baixa o cadastro imobiliário da prefeitura e o grava por endereço.

O CKAN publica um CSV por regional, mensal, e cada um chega a cinquenta
megabytes — mas o que sobra depois de agregar por endereço são dezenas de
milhares de linhas, não milhões. Cada arquivo é baixado para disco temporário,
agregado, e descartado; só o resultado vai para o banco.

O cadastro é um retrato do mês, não um diário: cada extração substitui a
anterior no mesmo endereço. O `upsert` mantém a linha viva e atualiza a
coordenada, o padrão e a contagem de unidades.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterable, Iterator
from datetime import date

import requests
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.pbh_registry import (
    CITY,
    CKAN_QUERY,
    CKAN_SEARCH,
    RegistryRow,
    _source_date,
    parse_file,
    resource_urls,
)
from app.models.registry_address import RegistryAddress

# ~17 colunas por linha, bem abaixo do teto de 65535 parâmetros do Postgres.
UPSERT_CHUNK = 1_000
DOWNLOAD_TIMEOUT = (30, 900)
# O CKAN da prefeitura responde 403 sem um agente de navegador.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ImovelRadar/1.0)"}


def _chunks[T](items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def discover_resources(query: str = CKAN_QUERY) -> dict[str, tuple[str, str]]:
    """Regional -> (data da extração, URL do CSV) mais recente."""
    resposta = requests.get(
        CKAN_SEARCH, params={"q": query, "rows": 50}, headers=HEADERS, timeout=(15, 120)
    )
    resposta.raise_for_status()
    return resource_urls(resposta.json())


def stream_resource(url: str, *, city: str = CITY, source_stamp: str | None = None) -> Iterator[RegistryRow]:
    """Baixa um CSV de regional para disco temporário e o lê.

    Ler direto do socket parece a economia óbvia e não é: envolver
    `response.raw` num `TextIOWrapper` faz o csv estourar em "I/O operation on
    closed file" quando a conexão termina antes de o leitor drenar o buffer, e
    partir a resposta em linhas por conta própria quebraria um campo com aspas.
    O arquivo maior tem cinquenta megabytes e é descartado ao final.
    """
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w+b") as destino:
        with requests.get(url, headers=HEADERS, stream=True, timeout=DOWNLOAD_TIMEOUT) as resposta:
            resposta.raise_for_status()
            for pedaco in resposta.iter_content(chunk_size=1 << 20):
                destino.write(pedaco)
        destino.flush()
        with open(destino.name, encoding="utf-8-sig", newline="") as texto:
            yield from parse_file(texto, city=city, source_stamp=source_stamp)


def save_addresses(db: Session, rows: Iterable[RegistryRow]) -> int:
    """Grava os endereços, atualizando o que já existe.

    O mesmo endereço pode aparecer em duas regionais quando a rua faz divisa,
    então a última leitura dentro da mesma execução prevalece — e não pode
    colidir dentro de um único `insert`, que o Postgres recusa.
    """
    unicos: dict[tuple, dict] = {}
    for row in rows:
        chave = (row.city, row.street_key, row.number_key, row.construction_type)
        unicos[chave] = row.__dict__.copy()

    valores = list(unicos.values())
    for chunk in _chunks(valores, UPSERT_CHUNK):
        stmt = insert(RegistryAddress).values(chunk)
        db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_registry_addresses_endereco",
                set_={
                    coluna: stmt.excluded[coluna]
                    for coluna in (
                        "street",
                        "street_number",
                        "postal_code",
                        "occupation_type",
                        "finish_standard",
                        "units_count",
                        "median_unit_area",
                        "unit_area_dispersion",
                        "lat",
                        "lon",
                        "source_date",
                    )
                },
            )
        )
    db.commit()
    return len(valores)


def latest_source_date(db: Session, city: str) -> date | None:
    """A extração mais recente já gravada para a cidade."""
    return db.scalar(
        select(func.max(RegistryAddress.source_date)).where(RegistryAddress.city == city)
    )


def sync_registry(
    db: Session,
    *,
    city: str = CITY,
    regional: str | None = None,
    skip_if_current: bool = False,
) -> dict:
    """Sincroniza todas as regionais, ou apenas uma.

    Os dez arquivos somam quase quatrocentos megabytes e a prefeitura publica
    uma extração por mês, então o ciclo diário passa `skip_if_current` e só
    baixa quando o CKAN oferece uma extração mais nova do que a gravada.

    A comparação é contra o que está publicado, não contra hoje: a extração
    nasce com dois meses de atraso, então medir a idade pelo calendário faria
    a baixa se repetir todo dia para sempre.
    """
    recursos = discover_resources()
    if regional:
        recursos = {nome: dados for nome, dados in recursos.items() if nome == regional}
    if skip_if_current and recursos:
        gravado = latest_source_date(db, city)
        publicado = _source_date(max(stamp for stamp, _ in recursos.values()))
        if gravado is not None and publicado is not None and gravado >= publicado:
            return {
                "city": city,
                "regionais": {},
                "enderecos": 0,
                "pulado": f"já em {gravado}, publicado {publicado}",
            }
    resumo: dict[str, int] = {}
    for nome, (stamp, url) in sorted(recursos.items()):
        linhas = stream_resource(url, city=city, source_stamp=stamp)
        resumo[nome] = save_addresses(db, linhas)
    return {"city": city, "regionais": resumo, "enderecos": sum(resumo.values())}
