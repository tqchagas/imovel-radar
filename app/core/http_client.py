"""Shared HTTP client for the portal collectors.

Collectors run unattended against three third-party gateways that throttle,
time out and occasionally 5xx. Without a retry a single blip turns a scheduled
collection into a partial one; without a pace limit a city-wide sweep is a few
thousand requests in a burst, which is what gets an IP blocked.
"""

from __future__ import annotations

import os
import random
import threading
import time

import requests

_session = requests.Session()


class PortalBlocked(RuntimeError):
    """The portal refused us: an expired session, or a rate limit we hit.

    Told apart from an ordinary error because the answer is different - stop
    asking. Draining a whole budget against a gateway that just said no is what
    turns a throttle into a block.
    """


# Retried: the gateway is busy or the connection died mid-flight. A 4xx other
# than 429 means the request itself is wrong, and repeating it will not help.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = int(os.getenv("HTTP_MAX_ATTEMPTS", "3"))
BACKOFF_SECONDS = float(os.getenv("HTTP_BACKOFF_SECONDS", "1.0"))
MAX_BACKOFF_SECONDS = float(os.getenv("HTTP_MAX_BACKOFF_SECONDS", "30"))
MIN_INTERVAL_SECONDS = float(os.getenv("HTTP_MIN_INTERVAL_SECONDS", "0.35"))

_pace_lock = threading.Lock()
_last_request_at = 0.0


def _pace(min_interval: float | None = None) -> None:
    """Keep a floor between consecutive requests, process-wide."""
    global _last_request_at
    interval = MIN_INTERVAL_SECONDS if min_interval is None else min_interval
    if interval <= 0:
        return
    with _pace_lock:
        wait = _last_request_at + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _retry_after(response: requests.Response) -> float | None:
    """Honour the gateway's own pace when it tells us one."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return min(float(raw), MAX_BACKOFF_SECONDS)
    except ValueError:
        return None


def _sleep_before_retry(attempt: int, response: requests.Response | None) -> None:
    if response is not None:
        told = _retry_after(response)
        if told is not None:
            time.sleep(told)
            return
    # Exponential, with jitter so parallel workers do not line up on the retry.
    delay = min(BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
    time.sleep(delay * (0.5 + random.random() / 2))


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
    timeout: float = 30,
    allow_redirects: bool = True,
    min_interval: float | None = None,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _pace(min_interval)
        try:
            response = _session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=timeout,
                allow_redirects=allow_redirects,
            )
        except (requests.Timeout, requests.ConnectionError) as error:
            last_error = error
            if attempt == MAX_ATTEMPTS:
                raise
            _sleep_before_retry(attempt, None)
            continue

        if response.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
            _sleep_before_retry(attempt, response)
            continue
        return response

    # Only reachable when every attempt raised; the last one re-raises above.
    raise last_error if last_error else RuntimeError("http_request_failed")
