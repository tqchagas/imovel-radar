"""Baixa as páginas de condomínio de que a nota precisa, e só elas.

São 19.117 páginas de Belo Horizonte, de quase um megabyte cada. Baixar todas
seria dezessete gigabytes para responder a uma pergunta que só interessa onde
existe anúncio: qual o número da rua deste prédio.

Então a coleta é dirigida pelo anúncio. O bairro está no fim do slug, antes do
hash, o que permite escolher o alvo sem abrir a página; a ordem é a dos bairros
com mais anúncio ativo sem número resolvido, e cada execução tem teto. O
`<lastmod>` do sitemap faz o resto: página já gravada e não alterada não volta.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.ingestion.quintoandar_condos import (
    SITEMAP_INDEX,
    CondoRow,
    condo_entries,
    parse_condo_page,
    sitemap_parts,
    slug_neighborhood,
)
from app.models.market_comparable import MarketComparable
from app.models.portal_building import PortalBuilding

logger = logging.getLogger(__name__)

# O mesmo ritmo do qpreço: uma página é o que um humano navegando dispara, e é
# essa ordem de grandeza que se imita. O sitemap existe para ser lido, mas o
# volume aqui é de milhares, não de dezenas.
MIN_INTERVAL_SECONDS = float(os.getenv("CONDO_MIN_INTERVAL_SECONDS", "1.0"))
DEFAULT_LIMIT = 500
HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": "Mozilla/5.0 (compatible; ImovelRadar/1.0)",
}
TIMEOUT = (15, 60)
# Portal recusando é resposta, não soluço: para a etapa em vez de gastar o
# resto do orçamento contra um gateway que acabou de negar.
BLOCKED_STATUS = frozenset({401, 403, 429})
# Três falhas seguidas de qualquer tipo também encerram: o que quer que tenha
# mudado do outro lado não vai se resolver dentro desta execução.
MAX_CONSECUTIVE_FAILURES = 3
# De quantas em quantas páginas gravar. Uma execução interrompida no meio tem
# de valer o que já leu.
SAVE_BATCH = 100


class PortalBlockedError(RuntimeError):
    """O portal recusou. Abortar a etapa, não repetir."""


def _get(url: str) -> str:
    resposta = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if resposta.status_code in BLOCKED_STATUS:
        raise PortalBlockedError(f"http_{resposta.status_code}")
    resposta.raise_for_status()
    return resposta.text


def pending_neighborhoods(db: Session, city_key: str) -> list[str]:
    """Bairros com anúncio ativo sem número, do mais carente ao menos.

    Um bairro fora desta lista não tem anúncio que a página mudaria de tier
    hoje; ele volta quando um anúncio aparecer lá.
    """
    linhas = db.execute(
        select(MarketComparable.bairro_normalizado)
        .where(MarketComparable.ativo.is_(True))
        .where(MarketComparable.cidade_normalizada == city_key)
        .where(MarketComparable.numero_normalizado.is_(None))
        .where(MarketComparable.bairro_normalizado.is_not(None))
        .group_by(MarketComparable.bairro_normalizado)
        .order_by(func.count(MarketComparable.id).desc())
    ).all()
    return [bairro for (bairro,) in linhas]


def known_pages(db: Session, city: str) -> dict[str, date | None]:
    """URL -> `lastmod` já gravado, para não rebaixar o que não mudou."""
    return {
        url: quando
        for url, quando in db.execute(
            select(PortalBuilding.url, PortalBuilding.source_lastmod).where(
                PortalBuilding.city == city
            )
        ).all()
    }


def select_targets(
    entries: Iterable[tuple[str, date | None]],
    bairros: list[str],
    *,
    conhecidos: dict[str, date | None],
    limit: int,
    city_slug: str,
) -> list[tuple[str, date | None]]:
    """As páginas a baixar nesta execução, na ordem da carência."""
    posicao = {bairro: indice for indice, bairro in enumerate(bairros)}
    candidatos: list[tuple[int, str, date | None]] = []
    for url, lastmod in entries:
        bairro = slug_neighborhood(url, city_slug)
        if bairro is None or bairro not in posicao:
            continue
        if url in conhecidos:
            gravado = conhecidos[url]
            # Sem data declarada não há como saber que mudou, e baixar de novo
            # repetiria para sempre a mesma resposta.
            if lastmod is None or (gravado is not None and gravado >= lastmod):
                continue
        candidatos.append((posicao[bairro], url, lastmod))
    candidatos.sort(key=lambda item: (item[0], item[1]))
    return [(url, lastmod) for _, url, lastmod in candidatos[: max(0, limit)]]


def save_buildings(db: Session, rows: Iterable[CondoRow]) -> int:
    """Grava os prédios, atualizando o que já existe."""
    unicos: dict[tuple[str, str], dict] = {}
    for row in rows:
        if row.external_id:
            unicos[(row.source, row.external_id)] = row.__dict__.copy()
    if not unicos:
        return 0

    dialeto = db.bind.dialect.name
    insert = sqlite_insert if dialeto == "sqlite" else postgresql_insert
    for valores in unicos.values():
        stmt = insert(PortalBuilding).values(**valores)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[PortalBuilding.source, PortalBuilding.external_id],
                set_={
                    coluna: stmt.excluded[coluna]
                    for coluna in valores
                    if coluna not in {"source", "external_id"}
                },
            )
        )
    db.commit()
    return len(unicos)


def sync_condos(
    db: Session,
    *,
    city: str = "belo_horizonte",
    city_slug: str = "belo-horizonte",
    limit: int = DEFAULT_LIMIT,
    fetch: Callable[[str], str] = _get,
    sleep: Callable[[float], None] = time.sleep,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Uma passada da coleta: escolhe os alvos, baixa, grava."""
    bairros = pending_neighborhoods(db, city)
    if not bairros:
        return {
            "city": city,
            "alvos": 0,
            "gravados": 0,
            "falhas": 0,
            "pulado": "nenhum bairro com anúncio sem número",
        }

    conhecidos = known_pages(db, city)
    # Uma execução de 2.500 páginas leva quarenta minutos, e uma transação de
    # leitura aberta esse tempo todo bloqueia DDL — uma migration que só some
    # colunas fica esperando pelo `ALTER TABLE ... ACCESS EXCLUSIVE` — além de
    # segurar o vacuum. Nada mais precisa desta leitura, então ela é fechada
    # antes da rede começar.
    db.rollback()

    entradas: list[tuple[str, date | None]] = []
    for parte in sitemap_parts(fetch(SITEMAP_INDEX)):
        sleep(MIN_INTERVAL_SECONDS)
        entradas.extend(condo_entries(fetch(parte), city_slug))

    alvos = select_targets(
        entradas, bairros, conhecidos=conhecidos, limit=limit, city_slug=city_slug
    )
    if progress:
        progress(
            f"[condo-sync] bairros={len(bairros)} sitemap={len(entradas)} alvos={len(alvos)}"
        )

    lote: list[CondoRow] = []
    gravados = falhas = seguidas = 0
    interrompido: str | None = None
    for indice, (url, lastmod) in enumerate(alvos, start=1):
        sleep(MIN_INTERVAL_SECONDS)
        try:
            pagina = fetch(url)
        except PortalBlockedError as erro:
            interrompido = f"bloqueado:{erro}"
            break
        except Exception as erro:  # noqa: BLE001 - contada e seguida
            falhas += 1
            seguidas += 1
            logger.warning("[condo-sync] status=error url=%s error=%s", url, erro)
            if seguidas >= MAX_CONSECUTIVE_FAILURES:
                interrompido = "falhas_seguidas"
                break
            continue
        seguidas = 0
        row = parse_condo_page(pagina, url, city=city, lastmod=lastmod)
        if row is None:
            falhas += 1
            continue
        lote.append(row)
        # Gravar em lote é o que faz uma execução interrompida no minuto trinta
        # valer os trinta minutos: sem isso, um bloqueio no fim joga fora tudo
        # o que já tinha sido lido.
        if len(lote) >= SAVE_BATCH:
            gravados += save_buildings(db, lote)
            lote = []
        if progress and indice % 50 == 0:
            progress(
                f"[condo-sync] {indice}/{len(alvos)} gravados={gravados + len(lote)} "
                f"falhas={falhas}"
            )

    gravados += save_buildings(db, lote)
    return {
        "city": city,
        "alvos": len(alvos),
        "gravados": gravados,
        "falhas": falhas,
        "interrompido": interrompido,
    }
