from app.market_collectors.quintoandar import collect
from app.market_collectors.normalize import canonical_scope_key
from app.market_collectors.normalize import safe_float, safe_int
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


def test_parses_auction_monitor_search_result_hits_shape(monkeypatch):
    payload = {
        "search": {
            "result": {
                "hits": [{
                    "_id": "895068389",
                    "_source": {
                        "id": 895068389,
                        "salePrice": 529000,
                        "area": 90,
                        "bedrooms": 3,
                        "type": "APARTMENT",
                        "neighbourhood": "Castelo",
                        "address": "Rua Sao Joao do Oriente, Castelo · Belo Horizonte",
                    },
                }]
            }
        }
    }
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, payload))
    result = collect(query(max_pages=1, bairro=None))
    assert len(result.listings) == 1
    assert result.listings[0].listing_id == "895068389"
    assert result.listings[0].rua == "Rua Sao Joao do Oriente"
    assert result.listings[0].bairro == "Castelo"


def test_reads_nested_hits_total_and_ends_at_known_total(monkeypatch):
    payload = {"search": {"result": {"hits": {"total": {"value": 100}, "hits": [item(str(i)) for i in range(100)]}}}}
    calls = []
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: (calls.append(k) or Response(200, payload)))
    result = collect(query(max_pages=1, bairro=None))
    assert result.success is True
    assert result.partial is False
    assert result.total == 100
    assert len(calls) == 1


def test_preserves_known_zero_total(monkeypatch):
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, {"search": {"result": {"hits": {"total": {"value": 0}, "hits": []}}}}))
    result = collect(query(max_pages=1))
    assert result.success is True
    assert result.total == 0


def test_elasticsearch_gte_total_does_not_end_as_complete(monkeypatch):
    payload = {"search": {"result": {"hits": {"total": {"value": 100, "relation": "gte"}, "hits": [item(str(i)) for i in range(100)]}}}}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, payload))
    result = collect(query(max_pages=1, bairro=None))
    assert result.partial is True
    assert result.success is False
    assert result.total is None


def test_preserves_total_when_later_page_omits_it(monkeypatch):
    responses = iter([
        Response(200, {"search": {"result": {"totalCount": 2, "hits": [item()]}}}),
        Response(200, {"search": {"result": {"hits": []}}}),
    ])
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: next(responses))
    result = collect(query(max_pages=2))
    assert result.success is True
    assert result.total == 2


def test_ignores_repeated_ids_and_missing_or_rent_prices(monkeypatch):
    payload = {"hits": [item(), item("qa-1", salePrice=800000), item("qa-no-price", salePrice=None), item("qa-rent", salePrice=None, rent=2500)]}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, payload))
    result = collect(query(max_pages=1))
    assert [listing.listing_id for listing in result.listings] == ["qa-1"]


def test_requires_explicit_sale_price(monkeypatch):
    payload = {"hits": [item(salePrice=None, price=123000)]}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, payload))
    assert collect(query(max_pages=1)).listings == []


def test_total_counts_valid_items_even_when_ids_repeat(monkeypatch):
    responses = iter([
        Response(200, {"hits": [item("qa-1"), item("qa-1")], "total": 3}),
        Response(200, {"hits": [item("qa-2")], "total": 3}),
    ])
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: next(responses))
    result = collect(query(max_pages=2))
    assert result.success is False
    assert result.partial is True
    assert [listing.listing_id for listing in result.listings] == ["qa-1", "qa-2"]


def test_invalid_json_http_error_and_full_page_without_total_are_partial_or_fatal(monkeypatch):
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, None, True))
    invalid = collect(query(max_pages=1))
    assert invalid.success is False and invalid.error

    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(503, {}))
    failed = collect(query(max_pages=1))
    assert failed.success is False and failed.partial is True and failed.error


def test_http_failure_on_first_page_is_partial(monkeypatch):
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(503, {}))
    result = collect(query())
    assert result.success is False and result.partial is True and result.pages == 0

    page = {"hits": [item(str(i)) for i in range(100)]}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, page))
    partial = collect(query(max_pages=1))
    assert partial.success is False and partial.partial is True


def test_scope_key_is_stable():
    assert canonical_scope_key(query(), "quintoandar").startswith("quintoandar:")


def test_applies_query_filters_to_request_and_scope(monkeypatch):
    calls = []
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: (calls.append(k) or Response(200, {"hits": []})))
    result = collect(query(tipo_imovel="casa", quartos=3, area_util_m2=120))
    body = calls[0]["json_body"]
    assert body["filters"]["propertyType"] == "HOUSE"
    assert body["filters"]["bedrooms"] == 3
    assert body["filters"]["area"] == 120
    assert '"tipo_imovel":"CASA"' in result.scope_key


def test_numeric_parser_preserves_decimal_and_brazilian_formats():
    assert safe_float("80.5") == 80.5
    assert safe_float("500000.00") == 500000.0
    assert safe_float("R$ 500.000,00") == 500000.0


def test_unknown_type_is_not_a_valid_type(monkeypatch):
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, {"hits": [item(type="PALACIO")] }))
    result = collect(query(max_pages=1))
    assert result.listings == []


def test_unknown_query_type_is_rejected(monkeypatch):
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, {"hits": []}))
    result = collect(query(tipo_imovel="palacio"))
    assert result.error == "unsupported_tipo_imovel"


def test_non_dictionary_items_are_structural_errors(monkeypatch):
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, {"hits": ["not-an-item"]}))
    assert collect(query()).error == "invalid_payload_structure"


def test_duplicate_ids_do_not_satisfy_source_total(monkeypatch):
    rows = [item(str(i)) for i in range(99)] + [item("0")]
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, {"hits": rows, "total": 100}))
    result = collect(query(max_pages=1))
    assert result.partial is True
    assert result.success is False
    assert len(result.listings) == 99


def test_rejects_invalid_positive_values_and_non_finite_coordinates(monkeypatch):
    assert safe_float("nan") is None
    assert safe_float("inf") is None
    assert safe_float("-1") is None
    assert safe_float("-1", positive=True) is None
    assert safe_float("0", positive=True) is None
    payload = {"hits": [item(area=-10, salePrice=0, latitude="nan", longitude="inf")]}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, payload))
    assert collect(query(max_pages=1)).listings == []


def test_rejects_listing_url_outside_portal_host(monkeypatch):
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, {"hits": [item(url="https://evil.example/listing")] }))
    assert collect(query(max_pages=1)).listings == []


def test_raw_payload_does_not_keep_sensitive_contact_fields(monkeypatch):
    payload = {"hits": [item(advertiserContact={"phones": ["5511999999999"], "email": "x@example.com"}, whatsappNumber="5511999999999")]}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, payload))
    raw = collect(query(max_pages=1)).listings[0].raw
    assert "advertiserContact" not in raw
    assert "whatsappNumber" not in raw


def test_numeric_parser_rejects_lixo_and_ambiguous_separators():
    assert safe_float("abc123") is None
    assert safe_float("12abc34") is None
    assert safe_float("1e3") is None
    assert safe_float("1.234") is None


def test_rejects_credentials_and_non_standard_ports_in_listing_url(monkeypatch):
    payloads = [
        {"hits": [item(url="https://user:pass@www.quintoandar.com.br/imovel/1")]},
        {"hits": [item(url="https://www.quintoandar.com.br:8443/imovel/1")]},
    ]
    for payload in payloads:
        monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, payload=payload, **k: Response(200, payload))
        assert collect(query(max_pages=1)).listings == []


def test_places_buy_path_before_query_string(monkeypatch):
    payload = {"hits": [item(url="/imovel/1?utm_source=x&foo=bar#tracking")]}
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: Response(200, payload))
    listing = collect(query(max_pages=1)).listings[0]
    assert listing.url == "https://www.quintoandar.com.br/imovel/1/comprar"


def test_safe_int_rejects_fractional_values():
    assert safe_int(2.9) is None
    assert safe_int("2.9") is None
    assert safe_int("2") == 2


def test_larger_earlier_total_is_not_replaced_by_smaller_later_total(monkeypatch):
    responses = iter([
        Response(200, {"hits": [item(str(i)) for i in range(50)], "total": 100}),
        Response(200, {"hits": [item("qa-last")], "total": 50}),
    ])
    monkeypatch.setattr("app.market_collectors.quintoandar.request", lambda *a, **k: next(responses))
    result = collect(query(max_pages=2))
    assert result.partial is True
    assert result.success is False
    assert result.total == 100
