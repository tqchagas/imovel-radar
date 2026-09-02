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

logger = logging.getLogger(__name__)

_URL = "https://apigw.prod.quintoandar.com.br/customer-facing-bff-api/pricing-reports/v1/price-suggestion"

# The endpoint answers anonymously; a session cookie changes nothing in the
# response. It is kept as an optional extra in case that ever stops being true.
# What the endpoint is not is paginated, so it gets a pace of its own instead of
# the collectors' floor: one estimate per listing is what a browsing human
# generates, and matching that order of magnitude is the whole tactic.
MIN_INTERVAL_SECONDS = float(os.getenv("QPRECO_MIN_INTERVAL_SECONDS", "3.0"))

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
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "origin": "https://www.quintoandar.com.br",
        "referer": "https://www.quintoandar.com.br/",
    }
    raw = settings.quintoandar_price_suggestion_cookie.strip()
    if raw:
        headers["cookie"] = f"5AJWT_AUTH={raw}" if "=" not in raw else raw
    return headers


def _build_body(listing_id: str) -> dict[str, Any]:
    """Only the id travels.

    The endpoint resolves the unit server-side and ignores everything else:
    doubling `total_area`, swapping in another listing's attributes, or dropping
    `price` altogether all return the same suggestion, and an id it does not
    know returns 404. The attribute mapping this used to carry was decorative.
    """
    return {"businessContext": "sale", "id": listing_id}


def extract_price_suggestion_fields(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "price_suggestion_json": json.dumps(data, ensure_ascii=False),
        "price_suggestion_lower_bound": _to_float_or_none(
            data.get("suggestedLowerBoundPrice")
        ),
        "price_suggestion_price": _to_float_or_none(data.get("suggestedPrice")),
        "price_suggestion_upper_bound": _to_float_or_none(
            data.get("suggestedUpperBoundPrice")
        ),
    }


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
    listing_id_str = str(listing_id or "").strip()
    if not listing_id_str:
        raise ValueError("listing_id is required")
    body = _build_body(listing_id_str)
    resp = request_fn(
        "POST",
        _URL,
        headers=_headers(),
        json_body=body,
        timeout=30,
        allow_redirects=True,
        min_interval=MIN_INTERVAL_SECONDS,
    )
    status_code = int(getattr(resp, "status_code", 0) or 0)
    text = str(getattr(resp, "text", "") or "")

    if status_code in (404, 415, 422):
        try:
            payload = resp.json() if text else {}
        except Exception:
            payload = {}
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("message") or payload.get("error") or "").strip()
        if not message:
            message = text[:500] or f"listing not supported (http_{status_code})"
        raise QuintoandarPriceSuggestionNotFound(message)

    if status_code in BLOCKED_STATUS:
        raise PortalBlocked(f"http_{status_code}:{text[:200]}")

    if status_code >= 400:
        raise RuntimeError(f"http_{status_code}:{text[:500]}")

    try:
        payload = resp.json() if text else {}
    except Exception as exc:
        raise RuntimeError(f"invalid_json:{exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("invalid_payload")
    return payload


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
