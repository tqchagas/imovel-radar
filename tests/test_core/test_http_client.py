import requests

from app.core import http_client


class Response:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def patch(monkeypatch, *, responses=None, no_pace=True):
    """Drive the client with a scripted sequence and no real waiting."""
    calls = []
    slept = []
    stream = iter(responses or [])

    def send(method, url, **kwargs):
        calls.append((method, url))
        item = next(stream)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(http_client._session, "request", send)
    monkeypatch.setattr(http_client.time, "sleep", lambda seconds: slept.append(seconds))
    if no_pace:
        monkeypatch.setattr(http_client, "MIN_INTERVAL_SECONDS", 0)
    return calls, slept


def test_successful_request_is_not_retried(monkeypatch):
    calls, slept = patch(monkeypatch, responses=[Response(200)])

    assert http_client.request("GET", "https://example.com").status_code == 200
    assert len(calls) == 1
    assert slept == []


def test_client_errors_are_returned_without_retrying(monkeypatch):
    # A 400 or 404 means the request itself is wrong; repeating it cannot help.
    for status in (400, 403, 404):
        calls, _ = patch(monkeypatch, responses=[Response(status)])
        assert http_client.request("GET", "https://example.com").status_code == status
        assert len(calls) == 1


def test_throttling_and_server_errors_are_retried(monkeypatch):
    for status in (429, 500, 502, 503, 504):
        calls, slept = patch(monkeypatch, responses=[Response(status), Response(200)])
        assert http_client.request("GET", "https://example.com").status_code == 200
        assert len(calls) == 2
        assert slept


def test_retries_stop_at_the_attempt_limit(monkeypatch):
    calls, _ = patch(monkeypatch, responses=[Response(503)] * http_client.MAX_ATTEMPTS)

    result = http_client.request("GET", "https://example.com")

    assert result.status_code == 503
    assert len(calls) == http_client.MAX_ATTEMPTS


def test_timeouts_are_retried_then_raised(monkeypatch):
    calls, _ = patch(monkeypatch, responses=[requests.Timeout(), Response(200)])
    assert http_client.request("GET", "https://example.com").status_code == 200
    assert len(calls) == 2

    calls, _ = patch(
        monkeypatch, responses=[requests.ConnectionError()] * http_client.MAX_ATTEMPTS
    )
    try:
        http_client.request("GET", "https://example.com")
    except requests.ConnectionError:
        pass
    else:
        raise AssertionError("the last failure must surface to the caller")
    assert len(calls) == http_client.MAX_ATTEMPTS


def test_retry_after_header_overrides_the_backoff(monkeypatch):
    _, slept = patch(
        monkeypatch,
        responses=[Response(429, {"Retry-After": "7"}), Response(200)],
    )

    http_client.request("GET", "https://example.com")

    assert slept == [7.0]


def test_absurd_retry_after_is_capped(monkeypatch):
    _, slept = patch(
        monkeypatch,
        responses=[Response(429, {"Retry-After": "99999"}), Response(200)],
    )

    http_client.request("GET", "https://example.com")

    assert slept == [http_client.MAX_BACKOFF_SECONDS]


def test_unparsable_retry_after_falls_back_to_the_backoff(monkeypatch):
    _, slept = patch(
        monkeypatch,
        responses=[Response(429, {"Retry-After": "in a while"}), Response(200)],
    )

    http_client.request("GET", "https://example.com")

    assert slept and slept[0] <= http_client.BACKOFF_SECONDS


def test_backoff_grows_between_attempts(monkeypatch):
    _, slept = patch(monkeypatch, responses=[Response(503), Response(503), Response(200)])

    http_client.request("GET", "https://example.com")

    assert len(slept) == 2
    assert slept[1] > slept[0]


def test_consecutive_requests_are_paced(monkeypatch):
    calls, slept = patch(
        monkeypatch, responses=[Response(200), Response(200)], no_pace=False
    )
    monkeypatch.setattr(http_client, "MIN_INTERVAL_SECONDS", 0.5)
    monkeypatch.setattr(http_client, "_last_request_at", 0.0)
    clock = iter([100.0, 100.0, 100.1, 100.5])
    monkeypatch.setattr(http_client.time, "monotonic", lambda: next(clock))

    http_client.request("GET", "https://example.com")
    http_client.request("GET", "https://example.com")

    # The second call starts 0.1s after the first, so it waits out the rest.
    assert len(calls) == 2
    assert slept and slept[0] > 0


def test_a_call_can_ask_for_a_slower_pace(monkeypatch):
    """The pricing endpoint is not paginated like the search ones, so it gets
    its own floor instead of the collector-wide default."""
    _, slept = patch(monkeypatch, responses=[Response(200), Response(200)], no_pace=False)
    monkeypatch.setattr(http_client, "MIN_INTERVAL_SECONDS", 0.01)

    http_client.request("POST", "https://example.com")
    http_client.request("POST", "https://example.com", min_interval=3.0)

    # The second call waits its own floor, not the collector-wide one.
    assert max(slept) > 1.0
