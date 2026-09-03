"""Abre e fecha os desfechos: anúncio que saiu do ar contra quitação de ITBI.

Duas etapas, deliberadamente separadas. Abrir é barato e acontece toda rodada,
logo depois da varredura: cada saída nova vira uma linha em aberto com o que o
modelo dizia naquele momento. Fechar depende do ITBI, que chega com dois meses
de atraso, então a mesma linha é reprocurada a cada rodada até encontrar par ou
envelhecer além da janela.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.buildings import BuildingIndex, buildings_from_rows
from app.domain.market_stats import Sale
from app.domain.opportunities import (
    RESIDENTIAL_OCCUPATION,
    address_key,
    itbi_construction_type,
)
from app.domain.outcomes import (
    LOOKAHEAD_DAYS,
    MATCH_BY_ADDRESS,
    MATCH_BY_COORDINATE,
    match_outcome,
)
from app.domain.slugs import street_key
from app.models.listing_outcome import ListingOutcome
from app.models.listing_price_event import ListingPriceEvent
from app.models.market_comparable import MarketComparable
from app.models.registry_address import RegistryAddress
from app.models.transaction import Transaction

DELISTED = "delisted"


def record_delistings(db: Session, *, city: str, since: datetime | None = None) -> int:
    """Abre um desfecho para cada saída de anúncio ainda não registrada.

    O evento de saída guarda o preço e a nota do momento; o endereço e a área
    ficam na linha do anúncio, que continua no banco com `ativo` falso. Um
    anúncio que sai, volta e sai de novo tem um desfecho por saída — são
    negócios diferentes, ou um que não se concretizou, e apagar essa distinção
    esconderia justamente o caso interessante.
    """
    stmt = (
        select(ListingPriceEvent, MarketComparable)
        .join(
            MarketComparable,
            (MarketComparable.source == ListingPriceEvent.source)
            & (MarketComparable.listing_id == ListingPriceEvent.listing_id),
        )
        .where(
            ListingPriceEvent.event == DELISTED,
            MarketComparable.cidade_normalizada == city,
        )
    )
    if since is None:
        # Sem corte, cada rodada relê o histórico inteiro para reinserir o que
        # o `on_conflict_do_nothing` já vai descartar. A última saída registrada
        # é o corte natural, e `>=` a inclui de novo de propósito: eventos com o
        # mesmo instante seriam perdidos por `>`.
        since = db.scalar(
            select(func.max(ListingOutcome.delisted_at)).where(ListingOutcome.city == city)
        )
    if since is not None:
        stmt = stmt.where(ListingPriceEvent.observed_at >= since)

    linhas = []
    for evento, anuncio in db.execute(stmt).all():
        linhas.append(
            {
                "source": evento.source,
                "listing_id": evento.listing_id,
                "city": city,
                "delisted_at": evento.observed_at,
                "preco_anunciado": evento.preco_total or anuncio.preco_total,
                "preco_estimado": anuncio.preco_estimado,
                "desconto_pct": evento.desconto_pct,
                "nota": evento.nota,
                "tipo_referencia": anuncio.tipo_referencia,
            }
        )
    if not linhas:
        return 0
    stmt_insert = insert(ListingOutcome).values(linhas)
    # Reabrir a mesma saída não pode sobrescrever um desfecho já fechado.
    db.execute(stmt_insert.on_conflict_do_nothing(constraint="uq_listing_outcomes_saida"))
    db.commit()
    return len(linhas)


def _sales_by_address(db: Session, city: str) -> dict[tuple[str, str, str], list[Sale]]:
    rows = db.execute(
        select(Transaction).where(
            Transaction.city == city,
            Transaction.street_number.is_not(None),
        )
    ).scalars()
    por_endereco: dict[tuple[str, str, str], list[Sale]] = defaultdict(list)
    for row in rows:
        if (row.occupation_type or "").strip().upper() != RESIDENTIAL_OCCUPATION:
            continue
        construcao = (row.construction_type or "").strip().upper()
        rua = street_key(row.street)
        numero = address_key(row.street_number)
        if not construcao or not rua or not numero:
            continue
        por_endereco[(construcao, rua, numero)].append(
            Sale(
                neighborhood=row.neighborhood,
                street=row.street,
                street_number=row.street_number,
                settlement_date=row.settlement_date,
                declared_value=float(row.declared_value),
                built_area_acquired=(
                    float(row.built_area_acquired) if row.built_area_acquired else None
                ),
                construction_type=row.construction_type,
                occupation_type=row.occupation_type,
                transaction_id=row.id,
            )
        )
    return por_endereco


def match_pending_outcomes(db: Session, *, city: str, now: datetime | None = None) -> dict:
    """Procura a quitação de cada desfecho ainda em aberto.

    Um desfecho para de ser procurado quando a janela dele fecha inteira dentro
    do ITBI que já temos: até lá a ausência de par não é resposta, é só dado
    que ainda não chegou.
    """
    instante = now or datetime.now(timezone.utc)
    abertos = (
        db.execute(
            select(ListingOutcome).where(
                ListingOutcome.city == city, ListingOutcome.matched_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    resumo = {"abertos": len(abertos), "casados": 0, "ambiguos": 0, "sem_itbi_ainda": 0}
    if not abertos:
        return resumo

    ultimo_itbi = db.execute(
        select(Transaction.settlement_date)
        .where(Transaction.city == city)
        .order_by(Transaction.settlement_date.desc())
        .limit(1)
    ).scalar()
    if ultimo_itbi is None:
        resumo["sem_itbi_ainda"] = len(abertos)
        return resumo

    por_endereco = _sales_by_address(db, city)
    predios = BuildingIndex.build(
        buildings_from_rows(
            db.execute(select(RegistryAddress).where(RegistryAddress.city == city))
            .scalars()
            .all()
        )
    )
    anuncios = {
        (row.source, row.listing_id): row
        for row in db.execute(
            select(MarketComparable).where(MarketComparable.cidade_normalizada == city)
        ).scalars()
    }

    for desfecho in abertos:
        anuncio = anuncios.get((desfecho.source, desfecho.listing_id))
        if anuncio is None:
            continue
        saida = desfecho.delisted_at.date()
        if ultimo_itbi < saida + timedelta(days=LOOKAHEAD_DAYS):
            # A janela ainda não terminou dentro do ITBI publicado.
            resumo["sem_itbi_ainda"] += 1
            continue

        construcao = itbi_construction_type(anuncio.tipo_imovel)
        rua = street_key(anuncio.rua_normalizada or anuncio.rua)
        numero = anuncio.numero_normalizado or anuncio.numero
        metodo = MATCH_BY_ADDRESS
        if not numero and anuncio.lat is not None and anuncio.lon is not None:
            numero = predios.resolve(rua, float(anuncio.lat), float(anuncio.lon))
            metodo = MATCH_BY_COORDINATE
        if not construcao or not rua or not numero:
            continue

        achado = match_outcome(
            por_endereco.get((construcao, rua, address_key(numero)), []),
            delisted_on=saida,
            area_anunciada=float(anuncio.area_util_m2) if anuncio.area_util_m2 else None,
        )
        desfecho.matched_at = instante
        if achado is None:
            continue
        desfecho.transaction_id = achado.sale.transaction_id
        desfecho.settlement_date = achado.sale.settlement_date
        desfecho.valor_realizado = achado.sale.declared_value
        desfecho.match_method = metodo
        desfecho.candidatos = achado.candidatos
        resumo["casados"] += 1
        if achado.candidatos > 1:
            resumo["ambiguos"] += 1

    db.commit()
    return resumo
