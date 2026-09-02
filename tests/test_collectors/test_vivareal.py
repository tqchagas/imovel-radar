import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.market_collectors.types import MarketQuery
from app.market_collectors.vivareal import PAGE_SIZE, RESULT_CAP, collect

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "vivareal_listings_v4.json"


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


def item(listing_id="2846291156", **overrides):
    """A row shaped like `search.result.listings[].listing`."""
    value = {
        "id": listing_id,
        "listingType": "USED",
        "pricingInfos": [{"businessType": "SALE", "price": "1120000", "iptuPeriod": "Period_NONE"}],
        "usableAreas": ["85"],
        "unitTypes": ["APARTMENT"],
        "bedrooms": [3],
        "bathrooms": [2],
        "suites": [1],
        "parkingSpaces": [1],
        "address": {
            "street": "Rua Bernardo Guimarães",
            "streetNumber": "769",
            "neighborhood": "Savassi",
            "city": "Belo Horizonte",
            "zipCode": "30140090",
            "point": {"lat": -19.936, "lon": -43.937, "source": "GOOGLE"},
        },
    }
    value.update(overrides)
    return value


def payload(rows, total=None, links=None):
    listings = []
    for index, row in enumerate(rows):
        entry = {"listing": row}
        href = (links or {}).get(index, f"/imovel/apartamento-savassi-id-{row['id']}/")
        if href is not None:
            entry["link"] = {"href": href}
        listings.append(entry)
    result = {"listings": listings}
    if total is not None:
        result["totalCount"] = total
    return {"search": {"result": result}}


def responder(monkeypatch, *responses, urls=None):
    stream = iter(responses)

    def request(*args, **kwargs):
        if urls is not None:
            urls.append(args[1])
        return next(stream)

    monkeypatch.setattr("app.market_collectors.vivareal.request", request)


def params_of(url):
    return {key: value[0] for key, value in parse_qs(urlparse(url).query).items()}


def test_parses_the_real_captured_listings_response(monkeypatch):
    responder(monkeypatch, Response(200, json.loads(FIXTURE.read_text())))
    result = collect(query(max_pages=1))

    # The fixture's first row is a DEVELOPMENT advertising a price/area range.
    assert all(listing.listing_id != "2854207622" for listing in result.listings)
    assert result.listings
    listing = result.listings[0]
    assert listing.preco_total > 0
    assert listing.area_util_m2 > 0
    assert listing.tipo_imovel == "APARTAMENTO"
    assert listing.url.startswith("https://www.vivareal.com.br/")
    assert listing.cidade == "Belo Horizonte"


def test_sends_the_params_and_headers_the_gateway_requires(monkeypatch):
    urls = []
    responder(monkeypatch, Response(200, payload([], total=0)), urls=urls)
    collect(query(max_pages=1))

    params = params_of(urls[0])
    # Without categoryPage the gateway answers 500 however complete the rest is.
    assert params["categoryPage"] == "RESULT"
    assert params["business"] == "SALE"
    assert params["portal"] == "VIVAREAL"
    # The acronym silently returns zero results; only the full name matches.
    assert params["addressState"] == "Minas Gerais"
    assert params["addressCity"] == "Belo Horizonte"
    assert params["addressNeighborhood"] == "Savassi"
    assert params["addressType"] == "neighborhood"
    assert params["size"] == str(PAGE_SIZE)


def test_uses_title_cased_headers_that_cloudflare_accepts(monkeypatch):
    captured = {}

    def request(*args, **kwargs):
        captured.update(kwargs["headers"])
        return Response(200, payload([], total=0))

    monkeypatch.setattr("app.market_collectors.vivareal.request", request)
    collect(query(max_pages=1))

    # The all-lowercase form of these names is answered with 403.
    assert captured["X-Domain"] == "www.vivareal.com.br"
    assert "Accept" in captured and "User-Agent" in captured
    assert all(name == name.title() for name in captured)


def test_city_wide_query_omits_the_neighborhood(monkeypatch):
    urls = []
    responder(monkeypatch, Response(200, payload([], total=0)), urls=urls)
    collect(query(bairro=None, max_pages=1))

    params = params_of(urls[0])
    assert params["addressType"] == "city"
    assert "addressNeighborhood" not in params


def test_paginates_with_page_and_from_until_the_total_is_reached(monkeypatch):
    urls = []
    responder(
        monkeypatch,
        Response(200, payload([item(str(i)) for i in range(PAGE_SIZE)], total=PAGE_SIZE + 2)),
        Response(200, payload([item("b1"), item("b2")], total=PAGE_SIZE + 2)),
        urls=urls,
    )
    result = collect(query(max_pages=5))

    assert result.success is True
    assert result.partial is False
    assert len(result.listings) == PAGE_SIZE + 2
    assert params_of(urls[0])["from"] == "0"
    assert params_of(urls[1])["from"] == str(PAGE_SIZE)
    assert params_of(urls[1])["page"] == "2"


def test_scope_larger_than_the_gateway_cap_is_partial(monkeypatch):
    pages = RESULT_CAP // PAGE_SIZE
    responder(
        monkeypatch,
        *[Response(200, payload([item(f"p{page}-{i}") for i in range(PAGE_SIZE)], total=9000)) for page in range(pages)],
    )
    result = collect(query(max_pages=100))

    assert result.success is False
    assert result.partial is True
    assert result.error == "result_cap_reached"
    assert len(result.listings) == RESULT_CAP


def test_never_requests_past_the_cap(monkeypatch):
    pages = RESULT_CAP // PAGE_SIZE
    urls = []
    responder(
        monkeypatch,
        *[Response(200, payload([item(f"p{page}-{i}") for i in range(PAGE_SIZE)], total=9000)) for page in range(pages)],
        urls=urls,
    )
    collect(query(max_pages=100))

    assert len(urls) == pages
    assert all(int(params_of(url)["from"]) < RESULT_CAP for url in urls)


def test_development_rows_with_price_or_area_ranges_are_skipped(monkeypatch):
    rows = [
        item("range-areas", usableAreas=["66", "185"]),
        item("range-prices", pricingInfos=[
            {"businessType": "SALE", "price": "2474000"},
            {"businessType": "SALE", "price": "5021000"},
        ]),
        item("development", listingType="DEVELOPMENT"),
        item("usada"),
    ]
    responder(monkeypatch, Response(200, payload(rows, total=4)))
    result = collect(query(max_pages=1))

    assert [listing.listing_id for listing in result.listings] == ["usada"]


def test_rental_only_rows_are_skipped(monkeypatch):
    rows = [item("aluguel", pricingInfos=[{"businessType": "RENTAL", "price": "3200"}]), item("venda")]
    responder(monkeypatch, Response(200, payload(rows, total=2)))
    result = collect(query(max_pages=1))

    assert [listing.listing_id for listing in result.listings] == ["venda"]


def test_takes_the_listing_url_from_the_envelope_link(monkeypatch):
    responder(monkeypatch, Response(200, payload([item()], total=1, links={0: "/imovel/casa-id-1/?utm=x#frag"})))
    listing = collect(query(max_pages=1)).listings[0]

    assert listing.url == "https://www.vivareal.com.br/imovel/casa-id-1/"


def test_falls_back_to_an_id_url_when_the_envelope_has_no_link(monkeypatch):
    responder(monkeypatch, Response(200, payload([item("vr-9")], total=1, links={0: None})))
    listing = collect(query(max_pages=1)).listings[0]

    assert listing.url == "https://www.vivareal.com.br/imovel/id-vr-9/"


def test_rejects_listing_url_outside_the_portal_host(monkeypatch):
    responder(monkeypatch, Response(200, payload([item()], total=1, links={0: "https://evil.example/imovel/1"})))
    assert collect(query(max_pages=1)).listings == []


def test_rejects_credentials_and_non_standard_ports_in_listing_url(monkeypatch):
    for href in ("https://user:pass@www.vivareal.com.br/imovel/1", "https://www.vivareal.com.br:8443/imovel/1"):
        responder(monkeypatch, Response(200, payload([item()], total=1, links={0: href})))
        assert collect(query(max_pages=1)).listings == []


def test_approximate_coordinates_are_labelled(monkeypatch):
    row = item(address={
        "street": "Rua da Bahia", "neighborhood": "Centro", "city": "Belo Horizonte",
        "point": {"approximateLat": -19.92, "approximateLon": -43.94},
    })
    responder(monkeypatch, Response(200, payload([row], total=1)))
    listing = collect(query(max_pages=1)).listings[0]

    assert listing.coordinate_source == "APPROXIMATE"
    assert (listing.lat, listing.lon) == (-19.92, -43.94)


def test_applies_query_filters_to_the_request_and_scope(monkeypatch):
    urls = []
    responder(monkeypatch, Response(200, payload([], total=0)), urls=urls)
    result = collect(query(tipo_imovel="casa", quartos=3, area_util_m2=120))

    params = params_of(urls[0])
    assert params["unitTypes"] == "HOME"
    assert params["unitTypesV3"] == "HOME"
    assert params["bedrooms"] == "3"
    assert params["usableAreas"] == "120"
    assert '"tipo_imovel":"CASA"' in result.scope_key


def test_preserves_known_zero_total(monkeypatch):
    responder(monkeypatch, Response(200, payload([], total=0)))
    result = collect(query(max_pages=1))

    assert result.success is True
    assert result.total == 0


def test_ignores_repeated_ids(monkeypatch):
    responder(monkeypatch, Response(200, payload([item("vr-1"), item("vr-1")], total=2)))
    result = collect(query(max_pages=1))

    assert [listing.listing_id for listing in result.listings] == ["vr-1"]


def test_unknown_query_type_is_rejected(monkeypatch):
    responder(monkeypatch, Response(200, payload([], total=0)))
    assert collect(query(tipo_imovel="palacio")).error == "unsupported_tipo_imovel"


def test_http_failure_on_the_first_page_is_partial(monkeypatch):
    responder(monkeypatch, Response(503, {}))
    result = collect(query())

    assert result.success is False
    assert result.partial is True
    assert result.pages == 0
    assert result.error == "http_503"


def test_unexpected_payload_shapes_are_structural_errors(monkeypatch):
    for broken in ({"search": {"result": {"listings": "nope"}}}, {"search": {}}, {}, []):
        responder(monkeypatch, Response(200, broken))
        assert collect(query(max_pages=1)).error == "invalid_payload_structure"


def test_invalid_json_is_an_error(monkeypatch):
    responder(monkeypatch, Response(200, None, invalid_json=True))
    result = collect(query(max_pages=1))

    assert result.success is False
    assert result.error


def test_raw_payload_does_not_keep_sensitive_contact_fields(monkeypatch):
    row = item(advertiserContact={"phones": ["5511999999999"], "email": "x@example.com"}, whatsappNumber="5511999999999")
    responder(monkeypatch, Response(200, payload([row], total=1)))
    raw = collect(query(max_pages=1)).listings[0].raw

    assert "advertiserContact" not in raw
    assert "whatsappNumber" not in raw


def test_the_publication_date_travels_with_the_listing(monkeypatch):
    responder(monkeypatch, Response(200, payload([item(createdAt="2025-11-26T19:38:24.063Z")])))

    collected = collect(query(max_pages=1)).listings[0]

    assert collected.anunciado_em.year == 2025
    assert collected.anunciado_em.month == 11


def test_monthly_condo_fee_and_iptu_are_kept_in_monthly_terms(monkeypatch):
    # O VivaReal publica IPTU anual e o Loft publica mensal; a coluna guarda
    # mensal nas duas, senao os numeros nao se comparam.
    row = item(pricingInfos=[{
        "businessType": "SALE", "price": "1120000",
        "monthlyCondoFee": "1018", "yearlyIptu": "1200", "iptuPeriod": "YEARLY",
    }])
    responder(monkeypatch, Response(200, payload([row])))

    collected = collect(query(max_pages=1)).listings[0]

    assert collected.condominium_value == 1018.0
    assert collected.iptu_value == 100.0


def test_zeroed_costs_are_read_as_absent(monkeypatch):
    row = item(pricingInfos=[{
        "businessType": "SALE", "price": "1120000",
        "monthlyCondoFee": "0", "yearlyIptu": "0", "iptuPeriod": "Period_NONE",
    }])
    responder(monkeypatch, Response(200, payload([row])))

    collected = collect(query(max_pages=1)).listings[0]

    assert collected.condominium_value is None
    assert collected.iptu_value is None
