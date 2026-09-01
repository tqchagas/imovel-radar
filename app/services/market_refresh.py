from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Callable, Iterable

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.market_collectors import (
    CollectionResult,
    MarketQuery,
    NormalizedListing,
    collect_quintoandar,
    collect_vivareal,
)
from app.models.market_comparable import MarketComparable
from app.models.opportunity_alert import CollectionRun


def _address_key(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_") or None


def canonical_scope_key(
    *, source: str, uf: str, cidade: str, bairros: Iterable[str] = (), filtros: dict | None = None
) -> str:
    neighborhoods = sorted(
        {value.strip() for value in bairros if value and value.strip()}, key=str.casefold
    )
    payload = {
        "bairros": neighborhoods,
        "cidade": cidade.strip(),
        "filtros": filtros or {},
        "source": source.strip().lower(),
        "uf": uf.strip().upper(),
    }
    return f"{payload['source']}:{json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"


def _as_naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo else value


def _apply_listing(row: MarketComparable, item: NormalizedListing, scope_key: str, now: datetime) -> None:
    values = {
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
    }
    for key, value in values.items():
        setattr(row, key, value)


def refresh_market(
    db: Session,
    collection: CollectionResult,
    *,
    now: datetime | None = None,
    deactivate: bool = True,
) -> dict[str, int | str | bool]:
    timestamp = _as_naive(now or datetime.now(timezone.utc))
    run_status = "success" if collection.success and not collection.partial else "partial" if collection.partial else "failed"
    run = CollectionRun(
        source=collection.source,
        uf="",
        cidade="",
        bairros_json="[]",
        filtros_json="{}",
        scope_key=collection.scope_key,
        status=run_status,
        pages_count=collection.pages,
        error=collection.error,
        finished_at=timestamp,
    )
    db.add(run)

    seen_ids = {item.listing_id for item in collection.listings}
    for item in collection.listings:
        row = (
            db.query(MarketComparable)
            .filter_by(source=collection.source, listing_id=item.listing_id)
            .one_or_none()
        )
        if row is None:
            row = MarketComparable(
                source=collection.source,
                listing_id=item.listing_id,
                first_seen_at=timestamp,
            )
            db.add(row)
        _apply_listing(row, item, collection.scope_key, timestamp)

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
    return refresh_market(db, COLLECTORS[query.source](query), deactivate=deactivate)
