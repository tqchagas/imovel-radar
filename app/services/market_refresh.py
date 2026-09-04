from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import replace
from typing import Callable

from sqlalchemy import case, desc, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.domain.buildings import city_bounds, within_bounds
from app.domain.slugs import address_key, street_key
from app.models.registry_address import RegistryAddress
from app.market_collectors import (
    CollectionResult,
    MarketQuery,
    NormalizedListing,
    collect_loft,
    collect_quintoandar,
    collect_vivareal,
)
from app.market_collectors.normalize import canonical_scope_key, normalize_type, validate_query_filters
from app.models.listing_price_event import ListingPriceEvent
from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import CollectionRun

SUPPORTED_SOURCES = frozenset({"loft", "quintoandar", "vivareal"})


def _as_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def city_bounds_for(db: Session, city: str | None) -> tuple[float, float, float, float] | None:
    """A extensão da cidade, medida no cadastro imobiliário dela."""
    if not city:
        return None
    linha = db.execute(
        select(
            func.min(RegistryAddress.lat),
            func.max(RegistryAddress.lat),
            func.min(RegistryAddress.lon),
            func.max(RegistryAddress.lon),
        ).where(RegistryAddress.city == city, RegistryAddress.lat.is_not(None))
    ).one_or_none()
    if linha is None or linha[0] is None:
        return None
    return city_bounds([(float(linha[0]), float(linha[2])), (float(linha[1]), float(linha[3]))])


def _listing_values(
    item: NormalizedListing,
    scope_key: str,
    now: datetime,
    bounds: tuple[float, float, float, float] | None = None,
) -> dict:
    # Coordenada fora da cidade é erro do portal, não imóvel distante: a Loft
    # publica o centro geográfico do Brasil (-13,90 / -50,71) e pares
    # arredondados como -19 / -43 quando não sabe onde o imóvel fica, e chegou a
    # devolver pontos em Florianópolis e no Rio para endereços de Belo
    # Horizonte. Guardá-los faria a busca pelo prédio partir do lugar errado, e
    # bastava um deles para o mapa enquadrar meio país.
    dentro = within_bounds(item.lat, item.lon, bounds)
    return {
        "source": item.source,
        "listing_id": item.listing_id,
        "url": item.url,
        "cidade": item.cidade,
        "bairro": item.bairro,
        "rua": item.rua,
        "numero": item.numero,
        "cidade_normalizada": address_key(item.cidade),
        "bairro_normalizado": address_key(item.bairro),
        "rua_normalizada": street_key(item.rua),
        "numero_normalizado": address_key(item.numero),
        "tipo_imovel": item.tipo_imovel,
        "lat": item.lat if dentro else None,
        "lon": item.lon if dentro else None,
        "coordinate_source": item.coordinate_source if dentro else None,
        "condo_id": item.condo_id,
        "condo_name": item.condo_name,
        "area_origem": item.area_origem,
        "anunciado_em": item.anunciado_em,
        "condominium_value": item.condominium_value,
        "iptu_value": item.iptu_value,
        "bathrooms": item.bathrooms,
        "bedrooms": item.quartos,
        "parking_spaces": item.parking_spaces,
        "suites": item.suites,
        "area_util_m2": item.area_util_m2,
        "preco_total": item.preco_total,
        "ativo": True,
        "collection_scope_key": scope_key,
        "last_seen_at": now,
        "activation_event_id": 1,
    }


def _upsert_listing(db: Session, values: dict) -> None:
    dialect = db.bind.dialect.name
    insert = sqlite_insert if dialect == "sqlite" else postgresql_insert if dialect == "postgresql" else None
    if insert is None:
        raise RuntimeError(f"unsupported_database_dialect:{dialect}")

    statement = insert(MarketComparable).values(**values)
    updates = {
        key: getattr(statement.excluded, key)
        for key in values
        if key not in {"source", "listing_id", "first_seen_at", "activation_event_id"}
    }
    updates["activation_event_id"] = case(
        (MarketComparable.ativo.is_(False), MarketComparable.activation_event_id + 1),
        else_=MarketComparable.activation_event_id,
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[MarketComparable.source, MarketComparable.listing_id],
            set_=updates,
        )
    )


def _query_scope(query: MarketQuery) -> tuple[str, str, str, str]:
    bairros = list(query.bairros or ((query.bairro,) if query.bairro else ()))
    filtros = dict(query.filtros)
    for key in ("tipo_imovel", "quartos", "area_util_m2"):
        value = getattr(query, key)
        if value is not None:
            filtros[key] = value
    return (
        query.uf.strip().upper(),
        query.cidade.strip(),
        json.dumps(bairros, ensure_ascii=False, separators=(",", ":")),
        json.dumps(filtros, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _latest_valid_run(db: Session, source: str, scope_key: str) -> CollectionRun | None:
    return db.scalar(
        select(CollectionRun)
        .where(
            CollectionRun.source == source,
            CollectionRun.scope_key == scope_key,
            CollectionRun.status == "success",
        )
        .order_by(desc(CollectionRun.started_at), desc(CollectionRun.id))
        .limit(1)
    )


def _acquire_scope_lock(db: Session, source: str, scope_key: str) -> None:
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:scope_key))"), {"scope_key": f"{source}:{scope_key}"})
    elif dialect == "sqlite":
        if db.in_transaction():
            raise ValueError("SQLite transaction already active; rollback required before refresh")
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    else:
        raise RuntimeError(f"unsupported_database_dialect:{dialect}")


def _query_with_filters(query: MarketQuery) -> MarketQuery:
    validate_query_filters(query)
    values = {}
    for key in ("tipo_imovel", "quartos", "area_util_m2"):
        filtered = query.filtros.get(key)
        current = getattr(query, key)
        if filtered is None:
            continue
        if current is not None and (
            normalize_type(current) if key == "tipo_imovel" else current
        ) != (normalize_type(filtered) if key == "tipo_imovel" else filtered):
            raise ValueError(f"conflicting_filter:{key}")
        values[key] = filtered
    return replace(query, **values)


def _previous_state(db: Session, source: str, listing_ids: set[str]) -> dict[str, MarketComparable]:
    if not listing_ids:
        return {}
    rows = db.scalars(
        select(MarketComparable).where(
            MarketComparable.source == source,
            MarketComparable.listing_id.in_(listing_ids),
        )
    ).all()
    return {row.listing_id: row for row in rows}


def _record_price_event(
    db: Session,
    item: NormalizedListing,
    previous: MarketComparable | None,
    now: datetime,
) -> None:
    price = float(item.preco_total) if item.preco_total is not None else None
    if previous is None:
        event, before = "listed", None
    else:
        before = float(previous.preco_total) if previous.preco_total is not None else None
        if not previous.ativo:
            event = "relisted"
        elif before is not None and price is not None and abs(before - price) >= 0.01:
            event = "price_changed"
        else:
            # Same listing at the same price: nothing happened worth recording.
            return
    db.add(
        ListingPriceEvent(
            source=item.source,
            listing_id=item.listing_id,
            event=event,
            preco_total=price,
            preco_anterior=before,
            nota=previous.nota if previous is not None else None,
            nota_itbi=previous.nota_itbi if previous is not None else None,
            nota_qpreco=previous.nota_qpreco if previous is not None else None,
            desconto_pct=previous.desconto_pct if previous is not None else None,
            observed_at=now,
        )
    )


def _record_delistings(
    db: Session, source: str, scope_key: str, seen_ids: set[str], now: datetime
) -> None:
    """A listing that stops appearing is the closest observable proxy for a sale."""
    stmt = select(MarketComparable).where(
        MarketComparable.source == source,
        MarketComparable.collection_scope_key == scope_key,
        MarketComparable.ativo.is_(True),
    )
    if seen_ids:
        stmt = stmt.where(~MarketComparable.listing_id.in_(seen_ids))
    for row in db.scalars(stmt):
        db.add(
            ListingPriceEvent(
                source=row.source,
                listing_id=row.listing_id,
                event="delisted",
                preco_total=row.preco_total,
                preco_anterior=row.preco_total,
                nota=row.nota,
                nota_itbi=row.nota_itbi,
                nota_qpreco=row.nota_qpreco,
                desconto_pct=row.desconto_pct,
                observed_at=now,
            )
        )


def _collection_run(
    collection: CollectionResult,
    query: MarketQuery,
    started_at: datetime,
    finished_at: datetime,
) -> CollectionRun:
    uf, cidade, bairros_json, filtros_json = _query_scope(query)
    return CollectionRun(
        source=collection.source,
        uf=uf,
        cidade=cidade,
        bairros_json=bairros_json,
        filtros_json=filtros_json,
        scope_key=collection.scope_key,
        status="success" if collection.success and not collection.partial else "partial" if collection.partial else "failed",
        pages_count=collection.pages,
        error=collection.error,
        started_at=started_at,
        finished_at=finished_at,
    )


def refresh_market(
    db: Session,
    collection: CollectionResult,
    *,
    now: datetime | None = None,
    deactivate: bool = True,
    query: MarketQuery | None = None,
    started_at: datetime | None = None,
    commit: bool = True,
    lock: bool = True,
) -> dict[str, int | str | bool]:
    if query is None:
        raise ValueError("query is required")
    if collection.source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported source:{collection.source}")
    if query.source != collection.source:
        raise ValueError("query source does not match collection")
    validate_query_filters(query)
    if any(item.source != collection.source for item in collection.listings):
        raise ValueError("listing source does not match collection")
    expected_scope = canonical_scope_key(query, collection.source)
    if collection.scope_key != expected_scope:
        raise ValueError("scope_key does not match query")
    if lock:
        _acquire_scope_lock(db, collection.source, expected_scope)
    timestamp = _as_naive(now or datetime.now(timezone.utc))
    execution_started_at = _as_naive(started_at or timestamp)
    run_status = "success" if collection.success and not collection.partial else "partial" if collection.partial else "failed"
    previous_valid_run = _latest_valid_run(db, collection.source, expected_scope)
    if previous_valid_run and previous_valid_run.started_at >= execution_started_at:
        raise ValueError("stale refresh")
    run = _collection_run(collection, query, execution_started_at, timestamp)
    db.add(run)
    db.flush()
    if collection.success and not collection.partial:
        latest_run = _latest_valid_run(db, collection.source, expected_scope)
        if latest_run is not None and latest_run.id != run.id:
            if commit:
                db.rollback()
            raise ValueError("stale refresh")

    bounds = city_bounds_for(db, address_key(query.cidade))
    seen_ids = {item.listing_id for item in collection.listings}
    # Read the prior state before overwriting it: the movement between the two
    # is the only record of what a listing did, and the upsert erases it.
    previous = _previous_state(db, collection.source, seen_ids)
    for item in collection.listings:
        _record_price_event(db, item, previous.get(item.listing_id), timestamp)
        _upsert_listing(db, _listing_values(item, collection.scope_key, timestamp, bounds))

    deactivated = 0
    db.flush()
    latest_valid_run = _latest_valid_run(db, collection.source, collection.scope_key)
    can_deactivate = latest_valid_run is not None and latest_valid_run.id == run.id
    if deactivate and collection.success and not collection.partial and can_deactivate:
        statement = (
            update(MarketComparable)
            .where(
                MarketComparable.source == collection.source,
                MarketComparable.collection_scope_key == collection.scope_key,
                MarketComparable.ativo.is_(True),
            )
            .values(ativo=False)
        )
        if seen_ids:
            statement = statement.where(~MarketComparable.listing_id.in_(seen_ids))
        _record_delistings(db, collection.source, collection.scope_key, seen_ids, timestamp)
        deactivated = db.execute(statement).rowcount or 0

    latest_valid_run = _latest_valid_run(db, collection.source, collection.scope_key)
    if collection.success and not collection.partial and (
        latest_valid_run is None or latest_valid_run.id != run.id
    ):
        if commit:
            db.rollback()
        raise ValueError("stale refresh")
    if commit:
        db.commit()
    return {
        "source": collection.source,
        "status": run_status,
        "seen": len(seen_ids),
        "deactivated": deactivated,
        "scope_key": collection.scope_key,
    }


COLLECTORS: dict[str, Callable[[MarketQuery], CollectionResult]] = {
    "loft": collect_loft,
    "quintoandar": collect_quintoandar,
    "vivareal": collect_vivareal,
}


def collect_and_refresh(
    db: Session,
    query: MarketQuery,
    *,
    deactivate: bool = True,
) -> dict[str, int | str | bool]:
    query = _query_with_filters(query)
    if query.source not in SUPPORTED_SOURCES or query.source not in COLLECTORS:
        raise ValueError(f"unknown_source:{query.source}")
    neighborhoods = query.bairros or ((query.bairro,) if query.bairro else ())
    neighborhoods = neighborhoods or (None,)
    collected = []
    for neighborhood in neighborhoods:
        single_query = MarketQuery(
            uf=query.uf,
            cidade=query.cidade,
            bairro=neighborhood,
            tipo_imovel=query.tipo_imovel,
            quartos=query.quartos,
            area_util_m2=query.area_util_m2,
            max_pages=query.max_pages,
            source=query.source,
            filtros=query.filtros,
        )
        started_at = datetime.now(timezone.utc)
        collected.append((single_query, COLLECTORS[query.source](single_query), started_at))
    collected.sort(key=lambda item: item[1].scope_key)

    # An incomplete collection still carries listings that were really seen on
    # the portal, so they are stored. Both portals cap pagination well below the
    # size of a city-wide scope, which makes "partial" the normal outcome rather
    # than a failure - discarding it would keep the table permanently empty.
    # Deactivation stays gated on a complete snapshot inside refresh_market, so
    # a partial run can never retire a listing it was unable to page to.
    summaries = []
    if db.bind.dialect.name == "sqlite":
        _acquire_scope_lock(db, query.source, collected[0][1].scope_key)
        try:
            for single_query, collection, started_at in collected:
                summaries.append(
                    refresh_market(
                        db,
                        collection,
                        deactivate=deactivate,
                        query=single_query,
                        started_at=started_at,
                        commit=False,
                        lock=False,
                    )
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
    else:
        with db.begin():
            for single_query, collection, started_at in collected:
                summaries.append(
                    refresh_market(
                        db,
                        collection,
                        deactivate=deactivate,
                        query=single_query,
                        started_at=started_at,
                        commit=False,
                    )
                )
    statuses = {item["status"] for item in summaries}
    return {
        "source": query.source,
        "status": "success" if statuses == {"success"} else "failed" if statuses == {"failed"} else "partial",
        "seen": sum(int(item["seen"]) for item in summaries),
        "deactivated": sum(int(item["deactivated"]) for item in summaries),
        "scope_key": ",".join(str(item["scope_key"]) for item in summaries),
    }
