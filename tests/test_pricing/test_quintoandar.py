import json

import pytest

from app.models.market_comparable import MarketComparable
from app.pricing import quintoandar


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload) if payload is not None else ""

    def json(self) -> dict:
        return self._payload


def _row(**overrides) -> MarketComparable:
    defaults = dict(
        source="QUINTOANDAR",
        listing_id="abc123",
        cidade="SÃO PAULO",
        tipo_imovel="APARTAMENTO",
        lat=-23.5,
        lon=-46.6,
        bathrooms=2,
        bedrooms=3,
        parking_spaces=1,
        suites=1,
        area_util_m2=80.0,
        preco_total=500000.0,
        condominium_value=600.0,
        iptu_value=150.0,
    )
    defaults.update(overrides)
    return MarketComparable(**defaults)


def test_build_body_maps_fields():
    row = _row()
    body = quintoandar._build_body("abc123", row)
    assert body["id"] == "abc123"
    assert body["type"] == "APARTMENT"
    assert body["bedroom_count"] == 3
    assert body["bathroom_count"] == 2
    assert body["parking_slots_count"] == 1
    assert body["suite_count"] == 1
    assert body["total_area"] == 80.0
    assert body["price"] == 500000.0
    assert body["condominium_per_month"] == 600.0
    assert body["iptu_per_month"] == 150.0
    assert body["city"] == "São Paulo"


def test_build_body_without_row_has_minimal_fields():
    body = quintoandar._build_body("abc123", None)
    assert body == {"businessContext": "sale", "id": "abc123"}


def test_extract_price_suggestion_fields():
    payload = {
        "suggestedLowerBoundPrice": 480000,
        "suggestedPrice": 500000,
        "suggestedUpperBoundPrice": 520000,
    }
    extracted = quintoandar.extract_price_suggestion_fields(payload)
    assert extracted["price_suggestion_lower_bound"] == 480000.0
    assert extracted["price_suggestion_price"] == 500000.0
    assert extracted["price_suggestion_upper_bound"] == 520000.0
    assert json.loads(extracted["price_suggestion_json"]) == payload


def test_fetch_raises_not_found_on_404(monkeypatch):
    monkeypatch.setattr(
        quintoandar.settings, "quintoandar_price_suggestion_cookie", "token"
    )

    def fake_request(*args, **kwargs):
        return FakeResponse(404, {"message": "listing not found"})

    with pytest.raises(quintoandar.QuintoandarPriceSuggestionNotFound) as exc_info:
        quintoandar.fetch_quintoandar_price_suggestion(
            "abc123", request_fn=fake_request
        )
    assert exc_info.value.message == "listing not found"


def test_fetch_raises_on_server_error(monkeypatch):
    monkeypatch.setattr(
        quintoandar.settings, "quintoandar_price_suggestion_cookie", "token"
    )

    def fake_request(*args, **kwargs):
        return FakeResponse(500)

    with pytest.raises(RuntimeError, match="http_500"):
        quintoandar.fetch_quintoandar_price_suggestion(
            "abc123", request_fn=fake_request
        )


def test_fetch_returns_payload_on_success(monkeypatch):
    monkeypatch.setattr(
        quintoandar.settings, "quintoandar_price_suggestion_cookie", "token"
    )
    payload = {"suggestedPrice": 500000}

    def fake_request(*args, **kwargs):
        return FakeResponse(200, payload)

    result = quintoandar.fetch_quintoandar_price_suggestion(
        "abc123", request_fn=fake_request
    )
    assert result == payload


def test_headers_require_cookie(monkeypatch):
    monkeypatch.setattr(quintoandar.settings, "quintoandar_price_suggestion_cookie", "")
    with pytest.raises(RuntimeError, match="QUINTOANDAR_PRICE_SUGGESTION_COOKIE"):
        quintoandar._headers()


def test_enrich_updates_row_and_persists(db_session, monkeypatch):
    monkeypatch.setattr(
        quintoandar.settings, "quintoandar_price_suggestion_cookie", "token"
    )
    row = _row()
    db_session.add(row)
    db_session.commit()

    def fake_request(*args, **kwargs):
        return FakeResponse(200, {"suggestedPrice": 500000})

    result = quintoandar.enrich_quintoandar_price_suggestions(
        db_session, request_fn=fake_request
    )
    assert result["updated"] == 1
    assert result["failed"] == 0
    db_session.refresh(row)
    assert row.price_suggestion_price == 500000.0


def test_enrich_marks_terminal_not_found(db_session, monkeypatch):
    monkeypatch.setattr(
        quintoandar.settings, "quintoandar_price_suggestion_cookie", "token"
    )
    row = _row()
    db_session.add(row)
    db_session.commit()

    def fake_request(*args, **kwargs):
        return FakeResponse(404, {"message": "not supported"})

    result = quintoandar.enrich_quintoandar_price_suggestions(
        db_session, request_fn=fake_request
    )
    assert result["terminal"] == 1
    db_session.refresh(row)
    assert row.price_suggestion_price is None
    assert json.loads(row.price_suggestion_json)["message"] == "not supported"
