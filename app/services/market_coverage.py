"""Sweep a whole city without tripping the portals' pagination ceilings.

Every source caps how deep a single query can page - QuintoAndar at 1.000
results, VivaReal at 1.500, Loft at 9.000 - while Belo Horizonte alone carries
tens of thousands of listings per portal. A city-wide query therefore always
comes back truncated. The way through is to cut the city into scopes small
enough to be collected whole, and to cut again whenever one still reports that
it hit the ceiling.

Neighborhoods come from the ITBI table rather than from the portals: a listing
in a neighborhood with no transactions to compare against can never be scored,
so collecting it would only add noise.
"""

from __future__ import annotations

from dataclasses import replace

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.opportunities import RESIDENTIAL_OCCUPATION, window_bounds
from app.domain.slugs import address_key
from app.market_collectors.types import MarketQuery
from app.models.market_comparable import MarketComparable
from app.models.transaction import Transaction
from app.services.market_refresh import collect_and_refresh

# Split a scope that came back incomplete by bedroom count before giving up.
BEDROOM_SPLITS = (1, 2, 3, 4, 5)
MIN_NEIGHBORHOOD_SALES = 30


def neighborhoods_with_itbi(
    db: Session, city: str, *, min_sales: int = MIN_NEIGHBORHOOD_SALES
) -> list[str]:
    """Neighborhoods of the city with enough recent ITBI to score against."""
    city_key = address_key(city)
    if city_key is None:
        return []
    reference = db.scalar(
        select(func.max(Transaction.settlement_date)).where(Transaction.city == city_key)
    )
    if reference is None:
        return []
    start, end = window_bounds(reference)
    rows = db.execute(
        select(Transaction.neighborhood, func.count())
        .where(
            Transaction.city == city_key,
            func.upper(Transaction.occupation_type) == RESIDENTIAL_OCCUPATION,
            Transaction.declared_value > 0,
            Transaction.built_area_acquired > 0,
            Transaction.settlement_date >= start,
            Transaction.settlement_date <= end,
        )
        .group_by(Transaction.neighborhood)
        .having(func.count() >= min_sales)
        .order_by(func.count().desc())
    ).all()
    return [name for name, _ in rows if name and name.strip()]


def canonical_neighborhoods(db: Session, source: str, city: str) -> dict[str, str]:
    """Map a normalized neighborhood key to the spelling the portals answer to.

    ITBI stores names unaccented and upper-cased ("SANTO ANTONIO"). VivaReal
    matches `addressNeighborhood` exactly - "Santo Antônio" returns 2.584
    listings while "SANTO ANTONIO" returns zero *and a 200*, so passing the ITBI
    name through would quietly collect nothing. Listings already collected carry
    the portal's own spelling, so they are the lookup.
    """
    city_key = address_key(city)
    rows = db.execute(
        select(
            MarketComparable.bairro_normalizado,
            MarketComparable.bairro,
            MarketComparable.source,
        )
        .where(
            MarketComparable.cidade_normalizada == city_key,
            MarketComparable.bairro.is_not(None),
        )
        .distinct()
    ).all()
    # Every portal writes proper Portuguese, so a name learned from one fills
    # the gap for another. The source's own spelling still wins where both
    # exist.
    found: dict[str, str] = {}
    for key, name, row_source in rows:
        name = (name or "").strip()
        if not key or not name:
            continue
        if row_source == source or key not in found:
            found[key] = name
    return found


def sweep_city(
    db: Session,
    query: MarketQuery,
    *,
    neighborhoods: list[str] | None = None,
    deactivate: bool = True,
    split_on_cap: bool = True,
    progress=None,
) -> dict:
    """Collect a city one neighborhood at a time, splitting what stays capped.

    One neighborhood failing must not abort the sweep: each scope is committed
    on its own, and a failure is recorded and stepped over.
    """
    log = progress or (lambda message: None)
    names = neighborhoods if neighborhoods is not None else neighborhoods_with_itbi(db, query.cidade)
    canonical = canonical_neighborhoods(db, query.source, query.cidade)
    # The lookup leaves a read transaction open; the refresh below opens its own.
    db.rollback()
    report = {
        "source": query.source,
        "neighborhoods": len(names),
        "collected": 0,
        "capped": 0,
        "empty": 0,
        "failed": 0,
        "seen": 0,
        "scopes": [],
    }

    for name in names:
        portal_name = canonical.get(address_key(name), name)
        scoped = replace(query, bairro=None, bairros=(portal_name,))
        summaries = _collect_scope(db, scoped, deactivate=deactivate, log=log)

        if split_on_cap and any(item.get("status") == "capped" for item in summaries):
            log(f"{portal_name}: acima do teto, dividindo por quartos")
            summaries = []
            for bedrooms in BEDROOM_SPLITS:
                split = replace(scoped, quartos=bedrooms)
                summaries.extend(_collect_scope(db, split, deactivate=deactivate, log=log))

        for item in summaries:
            report["scopes"].append(item)
            report["seen"] += int(item.get("seen") or 0)
            if item["status"] == "failed":
                report["failed"] += 1
            elif item["status"] == "capped":
                report["capped"] += 1
            elif item["status"] == "empty":
                report["empty"] += 1
            else:
                report["collected"] += 1
    return report


def _collect_scope(db: Session, query: MarketQuery, *, deactivate: bool, log) -> list[dict]:
    label = f"{query.bairros[0] if query.bairros else query.cidade}"
    if query.quartos is not None:
        label = f"{label} / {query.quartos}q"
    try:
        summary = collect_and_refresh(db, query, deactivate=deactivate)
    except Exception as error:  # noqa: BLE001 - one scope must not stop the sweep
        db.rollback()
        log(f"{label}: erro {type(error).__name__}")
        return [{"scope": label, "status": "failed", "seen": 0, "error": str(error)}]

    # "partial" covers both a ceiling and a transport failure. Splitting is the
    # right answer either way: a smaller scope both fits and retries.
    status = "capped" if summary["status"] == "partial" else summary["status"]
    # A portal answering 200 with nothing in it is not a collected scope. It
    # usually means the neighborhood name did not match, and counting it as a
    # success is how a sweep reports covering a city it never touched.
    if status == "success" and not summary["seen"]:
        status = "empty"
    log(f"{label}: {status} seen={summary['seen']}")
    return [{"scope": label, "status": status, "seen": summary["seen"]}]
