from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_client import PortalBlocked
from app.core.http_client import request as default_request
from app.models.market_comparable import MarketComparable
from quintoandar import QuintoAndarClient
from quintoandar.errors import ListingNotFound as PackageListingNotFound
from quintoandar.errors import PortalBlocked as PackagePortalBlocked
from quintoandar.pricing import (
    MIN_INTERVAL_SECONDS as MIN_INTERVAL_SECONDS,
    URL as _URL,
    extract_price_suggestion as _extract_price_suggestion,
    price_suggestion_body as _price_suggestion_body,
    price_suggestion_headers as _price_suggestion_headers,
)

logger = logging.getLogger(__name__)

# The endpoint answers anonymously; a session cookie changes nothing in the
# response. It is kept as an optional extra in case that ever stops being true.
# What the endpoint is not is paginated, so it gets a pace of its own instead of
# the collectors' floor: one estimate per listing is what a browsing human
# generates, and matching that order of magnitude is the whole tactic.
# The portal refusing us is an answer, not a hiccup: stop, do not spend the
# rest of the budget on it.
BLOCKED_STATUS = frozenset({401, 403, 429})

class QuintoandarPriceSuggestionNotFound(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _headers() -> dict[str, str]:
    return _price_suggestion_headers(settings.quintoandar_price_suggestion_cookie)


def _build_body(listing_id: str) -> dict[str, Any]:
    """Only the id travels.

    The endpoint resolves the unit server-side and ignores everything else:
    doubling `total_area`, swapping in another listing's attributes, or dropping
    `price` altogether all return the same suggestion, and an id it does not
    know returns 404. The attribute mapping this used to carry was decorative.
    """
    return _price_suggestion_body(listing_id)


def extract_price_suggestion_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    return _extract_price_suggestion(payload)


def _terminal_not_found_payload(message: str) -> str:
    return json.dumps(
        {"error": "not_found", "status_code": 404, "message": message},
        ensure_ascii=False,
    )


def fetch_quintoandar_price_suggestion(
    listing_id: str,
    *,
    request_fn: Callable[..., Any] = default_request,
) -> dict[str, Any]:
    try:
        return QuintoAndarClient(
            request_fn,
            price_suggestion_cookie=settings.quintoandar_price_suggestion_cookie,
        ).price_suggestion(listing_id)
    except PackageListingNotFound as error:
        message = str(error).split(": ", 1)[-1]
        raise QuintoandarPriceSuggestionNotFound(message) from error
    except PackagePortalBlocked as error:
        raise PortalBlocked(str(error)) from error


def _store_payload(row: MarketComparable, payload: dict[str, Any]) -> dict[str, Any]:
    extracted = extract_price_suggestion_fields(payload)
    row.price_suggestion_json = extracted["price_suggestion_json"]
    row.price_suggestion_lower_bound = extracted["price_suggestion_lower_bound"]
    row.price_suggestion_price = extracted["price_suggestion_price"]
    row.price_suggestion_upper_bound = extracted["price_suggestion_upper_bound"]
    row.price_suggestion_updated_at = _now()
    return extracted


def _store_not_found(row: MarketComparable, message: str) -> None:
    row.price_suggestion_json = _terminal_not_found_payload(message)
    row.price_suggestion_lower_bound = None
    row.price_suggestion_price = None
    row.price_suggestion_upper_bound = None
    row.price_suggestion_updated_at = _now()


def price_suggestion_updater(
    request_fn: Callable[..., Any] = default_request,
) -> Callable[[MarketComparable], bool]:
    """Build the one-row fetcher the opportunity refresh injects.

    Returns True when a suggestion was stored. A listing QuintoAndar refuses to
    price is recorded as such and reported as False - it is an answer, not a
    failure. Anything else raises, so the caller can count it and move on.
    """

    def update(row: MarketComparable) -> bool:
        listing_id = str(row.listing_id or "").strip()
        try:
            payload = fetch_quintoandar_price_suggestion(listing_id, request_fn=request_fn)
        except QuintoandarPriceSuggestionNotFound as error:
            _store_not_found(row, error.message)
            return False
        _store_payload(row, payload)
        return True

    return update


def enrich_quintoandar_price_suggestions(
    session: Session,
    *,
    limit: int = 100,
    workers: int = 1,
    worker_index: int = 0,
    cidades: Sequence[str] | None = None,
    request_fn: Callable[..., Any] = default_request,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    batch_limit = max(1, int(limit))
    workers_count = max(1, int(workers))
    worker_slot = max(0, int(worker_index))
    if worker_slot >= workers_count:
        raise ValueError("worker_index must be less than workers")

    cidades_norm = sorted(
        {str(c or "").strip().upper() for c in (cidades or []) if str(c or "").strip()}
    )

    stmt = (
        select(MarketComparable)
        .where(func.upper(func.trim(MarketComparable.source)) == "QUINTOANDAR")
        .where(MarketComparable.listing_id.is_not(None))
        .where(func.length(func.trim(MarketComparable.listing_id)) > 0)
        .where(MarketComparable.price_suggestion_json.is_(None))
    )
    if cidades_norm:
        stmt = stmt.where(func.upper(func.trim(MarketComparable.cidade)).in_(cidades_norm))
    if workers_count > 1:
        stmt = stmt.where((MarketComparable.id % workers_count) == worker_slot)
    stmt = stmt.order_by(MarketComparable.id.asc()).limit(batch_limit)

    rows = list(session.execute(stmt).scalars())
    if progress:
        progress(
            f"[qa-price-suggestion] selected={len(rows)} limit={batch_limit} "
            f"worker={worker_slot + 1}/{workers_count} "
            f"cidades={','.join(cidades_norm) if cidades_norm else '-'}"
        )

    ok = fail = terminal = skipped = 0
    errors: list[dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        listing_id = str(row.listing_id or "").strip()
        if not listing_id:
            skipped += 1
            if progress:
                progress(
                    f"[qa-price-suggestion] item={idx}/{len(rows)} id={row.id} "
                    "status=skipped reason=missing-listing-id"
                )
            continue

        if progress:
            progress(
                f"[qa-price-suggestion] item={idx}/{len(rows)} id={row.id} "
                f"listing_id={listing_id} status=running"
            )
        try:
            payload = fetch_quintoandar_price_suggestion(listing_id, request_fn=request_fn)
            extracted = _store_payload(row, payload)
            session.commit()
            ok += 1
            logger.info(
                "[qa-price-suggestion] status=ok market_comparable_id=%s listing_id=%s",
                row.id,
                listing_id,
            )
            if progress:
                progress(
                    f"[qa-price-suggestion] item={idx}/{len(rows)} id={row.id} "
                    f"listing_id={listing_id} status=ok "
                    f"suggested_price={extracted['price_suggestion_price']}"
                )
        except QuintoandarPriceSuggestionNotFound as exc:
            terminal += 1
            _store_not_found(row, exc.message)
            session.commit()
            logger.info(
                "[qa-price-suggestion] status=terminal_not_found "
                "market_comparable_id=%s listing_id=%s",
                row.id,
                listing_id,
            )
            if progress:
                progress(
                    f"[qa-price-suggestion] item={idx}/{len(rows)} id={row.id} "
                    f"listing_id={listing_id} status=terminal_not_found"
                )
        except Exception as exc:
            fail += 1
            errors.append({"id": int(row.id), "listing_id": listing_id, "error": str(exc)})
            logger.warning(
                "[qa-price-suggestion] status=error market_comparable_id=%s "
                "listing_id=%s error=%s",
                row.id,
                listing_id,
                exc,
            )
            if progress:
                progress(
                    f"[qa-price-suggestion] item={idx}/{len(rows)} id={row.id} "
                    f"listing_id={listing_id} status=error error={exc}"
                )

    return {
        "selected": len(rows),
        "updated": ok,
        "failed": fail,
        "terminal": terminal,
        "skipped": skipped,
        "errors": errors[:20],
    }
