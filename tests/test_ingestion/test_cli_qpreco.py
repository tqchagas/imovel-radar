"""The CLI decides whether the opportunity refresh may call QuintoAndar."""

from app.core.config import settings
from app.ingestion.cli import qpreco_fetcher


def test_no_fetcher_when_the_qpreco_is_turned_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "quintoandar_price_suggestion_cookie", "token")

    assert qpreco_fetcher(False) is None


def test_a_fetcher_is_built_when_the_cookie_is_present(monkeypatch) -> None:
    monkeypatch.setattr(settings, "quintoandar_price_suggestion_cookie", "token")

    assert callable(qpreco_fetcher(True))


def test_a_fetcher_is_built_without_a_cookie(monkeypatch) -> None:
    monkeypatch.setattr(settings, "quintoandar_price_suggestion_cookie", "  ")

    # The price-suggestion endpoint answers anonymously; the session cookie is
    # an optional extra, not a requirement.
    assert callable(qpreco_fetcher(True))
