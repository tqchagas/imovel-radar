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


def test_the_body_carries_only_the_listing_id():
    # Medido contra o endpoint: a resposta nao muda ao dobrar a area, trocar
    # todos os atributos pelos de outro imovel, ou omitir o preco. Ele resolve
    # tudo pelo id do lado deles, e um id desconhecido devolve 404. Mandar
    # atributos e teatro.
    assert quintoandar._build_body("abc123") == {"businessContext": "sale", "id": "abc123"}


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


def test_headers_omit_the_cookie_when_there_is_no_session(monkeypatch):
    monkeypatch.setattr(quintoandar.settings, "quintoandar_price_suggestion_cookie", "  ")

    headers = quintoandar._headers()

    # The endpoint answers anonymously, so an absent cookie is a valid state.
    assert "cookie" not in headers
    assert headers["origin"] == "https://www.quintoandar.com.br"


def test_headers_carry_the_cookie_when_one_is_configured(monkeypatch):
    monkeypatch.setattr(quintoandar.settings, "quintoandar_price_suggestion_cookie", "token")

    assert quintoandar._headers()["cookie"] == "5AJWT_AUTH=token"


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


def test_updater_writes_the_suggestion_on_the_row(db_session, monkeypatch):
    monkeypatch.setattr(
        quintoandar.settings, "quintoandar_price_suggestion_cookie", "token"
    )
    row = _row()
    db_session.add(row)
    db_session.commit()

    def fake_request(*args, **kwargs):
        return FakeResponse(
            200,
            {
                "suggestedPrice": 500000,
                "suggestedLowerBoundPrice": 480000,
                "suggestedUpperBoundPrice": 520000,
            },
        )

    updated = quintoandar.price_suggestion_updater(request_fn=fake_request)(row)

    assert updated is True
    assert row.price_suggestion_price == 500000.0
    assert row.price_suggestion_lower_bound == 480000.0
    assert row.price_suggestion_updated_at is not None


def test_updater_marks_an_unsupported_listing_instead_of_raising(db_session, monkeypatch):
    monkeypatch.setattr(
        quintoandar.settings, "quintoandar_price_suggestion_cookie", "token"
    )
    row = _row()
    db_session.add(row)
    db_session.commit()

    def fake_request(*args, **kwargs):
        return FakeResponse(404, {"message": "not supported"})

    updated = quintoandar.price_suggestion_updater(request_fn=fake_request)(row)

    # A listing QuintoAndar cannot price is settled, not failed: the timestamp
    # keeps it out of the next run instead of retrying it forever.
    assert updated is False
    assert row.price_suggestion_price is None
    assert json.loads(row.price_suggestion_json)["error"] == "not_found"
    assert row.price_suggestion_updated_at is not None


def test_updater_propagates_a_server_error(db_session, monkeypatch):
    monkeypatch.setattr(
        quintoandar.settings, "quintoandar_price_suggestion_cookie", "token"
    )
    row = _row()

    def fake_request(*args, **kwargs):
        return FakeResponse(503)

    with pytest.raises(RuntimeError, match="http_503"):
        quintoandar.price_suggestion_updater(request_fn=fake_request)(row)


def test_a_refusal_is_reported_as_a_block(monkeypatch):
    monkeypatch.setattr(quintoandar.settings, "quintoandar_price_suggestion_cookie", "")
    row = _row()

    for status in (401, 403, 429):
        def fake_request(*args, _status=status, **kwargs):
            return FakeResponse(_status)

        # Blocks are told apart from ordinary errors so the caller can stop
        # asking instead of spending its whole budget against a closed door.
        with pytest.raises(quintoandar.PortalBlocked):
            quintoandar.price_suggestion_updater(request_fn=fake_request)(row)
