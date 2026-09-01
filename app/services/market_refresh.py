from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import case, update
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
from app.market_collectors.normalize import canonical_scope_key
from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import CollectionRun


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


def refresh_market(
    db: Session,
    collection: CollectionResult,
    *,
    now: datetime | None = None,
    deactivate: bool = True,
    query: MarketQuery | None = None,
) -> dict[str, int | str | bool]:
    if query is None:
        raise ValueError("query is required")
    timestamp = _as_naive(now or datetime.now(timezone.utc))
    run_status = "success" if collection.success and not collection.partial else "partial" if collection.partial else "failed"
    uf, cidade, bairros_json, filtros_json = _query_scope(query)
    run = CollectionRun(
        source=collection.source,
        uf=uf,
        cidade=cidade,
        bairros_json=bairros_json,
        filtros_json=filtros_json,
        scope_key=collection.scope_key,
        status=run_status,
        pages_count=collection.pages,
        error=collection.error,
        finished_at=timestamp,
    )
    db.add(run)

    seen_ids = {item.listing_id for item in collection.listings}
    for item in collection.listings:
        _upsert_listing(db, _listing_values(item, collection.scope_key, timestamp))

    deactivated = 0
    if deactivate and collection.success and not collection.partial:
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
    if query.source not in COLLECTORS:
        raise ValueError(f"unknown_source:{query.source}")
    return refresh_market(db, COLLECTORS[query.source](query), deactivate=deactivate, query=query)
