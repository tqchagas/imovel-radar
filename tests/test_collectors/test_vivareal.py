from app.market_collectors.types import MarketQuery
from app.market_collectors.vivareal import collect


class Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


def query(**overrides):
    values = {"uf": "MG", "cidade": "Belo Horizonte", "bairro": "Centro"}
    values.update(overrides)
    return MarketQuery(**values)


def item(listing_id="vr-1", **overrides):
    value = {
        "id": listing_id,
        "pricingInfos": [{"businessType": "SALE", "price": "R$ 500.000"}, {"businessType": "RENTAL", "price": 2000}],
        "usableAreas": [70],
        "unitTypes": ["APARTMENT"],
        "address": {"street": "Rua da Bahia", "streetNumber": "42", "neighborhood": "Centro", "city": "Belo Horizonte", "point": {"lat": -19.92, "lon": -43.94}},
        "link": {"href": "/imovel/vr-1"},
        "bedrooms": [2],
    }
    value.update(overrides)
    return value


def test_collects_glue_pages_and_sale_fields(monkeypatch):
    responses = iter([
        Response(200, {"search": {"result": {"listings": [item()]}, "total": 2}}),
        Response(200, {"search": {"result": {"listings": [item("vr-2", unitTypes=["HOUSE"])]}, "total": 2}}),
    ])
    calls = []

    def request(*args, **kwargs):
        calls.append(args[1])
        return next(responses)

    monkeypatch.setattr("app.market_collectors.vivareal.request", request)
    result = collect(query())
    assert result.success is True
    assert result.pages == 2
    listing = result.listings[0]
    assert listing.preco_total == 500000
    assert listing.area_util_m2 == 70
    assert listing.rua == "Rua da Bahia"
    assert listing.numero == "42"
    assert listing.tipo_imovel == "APARTAMENTO"
    assert listing.listing_id == "vr-1"
    assert listing.url == "https://www.vivareal.com.br/imovel/vr-1"
    assert (listing.lat, listing.lon) == (-19.92, -43.94)
    assert "page=2" in calls[1]


def test_reads_glue_result_total_count_and_ends_at_known_total(monkeypatch):
    payload = {"search": {"result": {"listings": [item(str(i)) for i in range(100)], "totalCount": 100}}}
    calls = []
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: (calls.append(a[1]) or Response(200, payload)))
    result = collect(query(max_pages=1))
    assert result.success is True
    assert result.partial is False
    assert result.total == 100
    assert len(calls) == 1


def test_preserves_known_zero_total(monkeypatch):
    payload = {"search": {"result": {"listings": [], "totalCount": 0}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, payload))
    result = collect(query(max_pages=1))
    assert result.success is True
    assert result.total == 0


def test_elasticsearch_gte_total_does_not_end_as_complete(monkeypatch):
    payload = {"search": {"result": {"totalCount": {"value": 100, "relation": "gte"}, "listings": [item(str(i)) for i in range(100)]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, payload))
    result = collect(query(max_pages=1))
    assert result.partial is True
    assert result.success is False
    assert result.total is None


def test_preserves_total_when_later_page_omits_it(monkeypatch):
    responses = iter([
        Response(200, {"search": {"result": {"totalCount": 2, "listings": [item()]}}}),
        Response(200, {"search": {"result": {"listings": []}}}),
    ])
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: next(responses))
    result = collect(query(max_pages=2))
    assert result.success is True
    assert result.total == 2


def test_maps_home_to_casa(monkeypatch):
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, {"search": {"result": {"listings": [item(unitTypes=["HOME"])]}}}))
    result = collect(query(max_pages=1))
    assert result.listings[0].tipo_imovel == "CASA"


def test_repeated_ids_missing_price_invalid_structure_and_page_limit(monkeypatch):
    payload = {"search": {"result": {"listings": [item(), item("vr-1", pricingInfos=[])]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, payload))
    result = collect(query(max_pages=1))
    assert [listing.listing_id for listing in result.listings] == ["vr-1"]

    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, {}))
    assert collect(query(max_pages=1)).error

    full = {"search": {"result": {"listings": [item(str(i)) for i in range(100)]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, full))
    assert collect(query(max_pages=1)).partial is True


def test_total_counts_valid_items_even_when_ids_repeat(monkeypatch):
    responses = iter([
        Response(200, {"search": {"result": {"listings": [item(), item("vr-1")]}, "total": 3}}),
        Response(200, {"search": {"result": {"listings": [item("vr-2")]}, "total": 3}}),
    ])
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: next(responses))
    result = collect(query(max_pages=2))
    assert result.success is False and result.partial is True
    assert [listing.listing_id for listing in result.listings] == ["vr-1", "vr-2"]


def test_invalid_json_and_http_status_are_fatal(monkeypatch):
    class Invalid:
        status_code = 200
        def json(self):
            raise ValueError("invalid")

    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Invalid())
    assert collect(query()).error
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(429, {}))
    result = collect(query())
    assert result.error and result.partial is True


def test_applies_query_filters_and_marks_approximate_coordinates(monkeypatch):
    calls = []
    payload = {"search": {"result": {"listings": [item(address={"point": {"approximateLat": -19.9, "approximateLon": -43.9}})]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: (calls.append(a[1]) or Response(200, payload)))
    result = collect(query(tipo_imovel="apartamento", quartos=2, area_util_m2=70, max_pages=1))
    assert result.listings[0].coordinate_source == "APPROXIMATE"
    assert "addressNeighborhood=Centro" in calls[0]
    assert "unitTypes=APARTMENT" in calls[0]
    assert "bedrooms=2" in calls[0]
    assert "usableAreas=70" in calls[0]


def test_non_dictionary_items_are_structural_errors(monkeypatch):
    payload = {"search": {"result": {"listings": ["not-an-item"]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, payload))
    assert collect(query()).error == "invalid_payload_structure"


def test_empty_pricing_infos_cannot_fall_back_to_generic_price(monkeypatch):
    payload = {"search": {"result": {"listings": [item(pricingInfos=[], price=123000)]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, payload))
    assert collect(query(max_pages=1)).listings == []


def test_uses_only_usable_area_and_rejects_invalid_values(monkeypatch):
    payload = {"search": {"result": {"listings": [item(usableAreas=[], totalAreas=[999], pricingInfos=[{"businessType": "SALE", "price": -1}])]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, payload))
    assert collect(query(max_pages=1)).listings == []


def test_rejects_listing_url_outside_portal_host(monkeypatch):
    payload = {"search": {"result": {"listings": [item(link={"href": "https://evil.example/listing"})]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, payload))
    assert collect(query(max_pages=1)).listings == []


def test_raw_payload_does_not_keep_sensitive_contact_fields(monkeypatch):
    payload = {"search": {"result": {"listings": [item(advertiserContact={"phones": ["5511999999999"]}, whatsappNumber="5511999999999")]}}}
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, payload))
    raw = collect(query(max_pages=1)).listings[0].raw
    assert "advertiserContact" not in raw
    assert "whatsappNumber" not in raw


def test_unknown_query_type_is_rejected(monkeypatch):
    monkeypatch.setattr("app.market_collectors.vivareal.request", lambda *a, **k: Response(200, {"search": {"result": {"listings": []}}}))
    assert collect(query(tipo_imovel="palacio")).error == "unsupported_tipo_imovel"
