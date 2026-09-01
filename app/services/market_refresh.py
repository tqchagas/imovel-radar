from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from dataclasses import replace
from typing import Callable

from sqlalchemy import case, desc, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.market_collectors import (
    CollectionResult,
    MarketQuery,
    NormalizedListing,
    collect_quintoandar,
    collect_vivareal,
)
from app.market_collectors.normalize import canonical_scope_key, normalize_type, validate_query_filters
from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import CollectionRun

SUPPORTED_SOURCES = frozenset({"quintoandar", "vivareal"})


def _address_key(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or None


def _as_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def _listing_values(item: NormalizedListing, scope_key: str, now: datetime) -> dict:
    return {
        "source": item.source,
        "listing_id": item.listing_id,
        "url": item.url,
        "cidade": item.cidade,
        "bairro": item.bairro,
        "rua": item.rua,
        "numero": item.numero,
        "cidade_normalizada": _address_key(item.cidade),
        "bairro_normalizado": _address_key(item.bairro),
        "rua_normalizada": _address_key(item.rua),
        "numero_normalizado": _address_key(item.numero),
        "tipo_imovel": item.tipo_imovel,
        "lat": item.lat,
        "lon": item.lon,
        "coordinate_source": item.coordinate_source,
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

    seen_ids = {item.listing_id for item in collection.listings}
    for item in collection.listings:
        _upsert_listing(db, _listing_values(item, collection.scope_key, timestamp))

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
    if not all(result.success and not result.partial for _, result, _ in collected):
        _acquire_scope_lock(db, query.source, collected[0][1].scope_key)
        try:
            finished_at = datetime.now(timezone.utc)
            for single_query, collection, started_at in collected:
                db.add(_collection_run(collection, single_query, started_at, finished_at))
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {
            "source": query.source,
            "status": "partial" if any(result.partial for _, result, _ in collected) else "failed",
            "seen": sum(len(result.listings) for _, result, _ in collected),
            "deactivated": 0,
            "scope_key": ",".join(result.scope_key for _, result, _ in collected),
        }

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
    return {
        "source": query.source,
        "status": "success" if all(item["status"] == "success" for item in summaries) else "partial",
        "seen": sum(int(item["seen"]) for item in summaries),
        "deactivated": sum(int(item["deactivated"]) for item in summaries),
        "scope_key": ",".join(str(item["scope_key"]) for item in summaries),
    }
