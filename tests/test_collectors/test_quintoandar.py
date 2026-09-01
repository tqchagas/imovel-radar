from app.market_collectors.quintoandar import collect
from app.market_collectors.normalize import canonical_scope_key
from app.market_collectors.types import MarketQuery


class Response:
    def __init__(self, status_code, payload=None, invalid_json=False):
        self.status_code = status_code
        self.payload = payload
        self.invalid_json = invalid_json

    def json(self):
        if self.invalid_json:
            raise ValueError("invalid json")
        return self.payload


def query(**overrides):
    values = {"uf": "MG", "cidade": "Belo Horizonte", "bairro": "Savassi"}
    values.update(overrides)
    return MarketQuery(**values)


def item(listing_id="qa-1", **overrides):
    value = {
        "id": listing_id,
        "salePrice": 720000,
        "area": 80,
        "type": "APARTMENT",
        "address": {"street": "Rua Pernambuco", "number": "100"},
        "neighbourhood": "Savassi",
        "url": f"/imovel/{listing_id}",
        "latitude": -19.936,
        "longitude": -43.935,
    }
    value.update(overrides)
    return value


def test_collects_pages_and_normalizes_sale_listing(monkeypatch):
    responses = iter([
        Response(200, {"hits": [item()], "total": 2}),
        Response(200, {"hits": [item("qa-2", type="HOUSE", salePrice=900000)], "total": 2}),
    ])
    calls = []

    def request(*args, **kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr("app.market_collectors.quintoandar.request", request)
    result = collect(query())

    assert result.success is True
    assert result.pages == 2
    assert len(result.listings) == 2
    first = result.listings[0]
    assert first.listing_id == "qa-1"
    assert first.url.endswith("/imovel/qa-1/comprar")
    assert first.preco_total == 720000
    assert first.area_util_m2 == 80
    assert first.rua == "Rua Pernambuco"
    assert first.numero == "100"
    assert (first.lat, first.lon) == (-19.936, -43.935)
    assert first.tipo_imovel == "APARTAMENTO"
    assert calls[0]["json_body"]["pagination"]["offset"] == 0
    assert calls[1]["json_body"]["pagination"]["offset"] > 0


def test_ignores_repeated_ids_and_missing_or_rent_prices(monkeypatch):
    payload = {"hits": [item(), item("qa-1", salePrice=800000), item("qa-no-price", salePrice=None), item("qa-rent", salePrice=None, rent=2500)]}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, payload))
    result = collect(query(max_pages=1))
    assert [listing.listing_id for listing in result.listings] == ["qa-1"]


def test_invalid_json_http_error_and_full_page_without_total_are_partial_or_fatal(monkeypatch):
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, None, True))
    invalid = collect(query(max_pages=1))
    assert invalid.success is False and invalid.error

    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(503, {}))
    failed = collect(query(max_pages=1))
    assert failed.success is False and failed.error

    page = {"hits": [item(str(i)) for i in range(100)]}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, page))
    partial = collect(query(max_pages=1))
    assert partial.success is False and partial.partial is True


def test_scope_key_is_stable():
    assert canonical_scope_key(query(), "quintoandar").startswith("quintoandar:")
