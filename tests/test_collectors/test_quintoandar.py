import json
from pathlib import Path

import pytest

from app.market_collectors.quintoandar import PAGE_SIZE, RESULT_CAP, _parse, collect
from app.market_collectors.normalize import canonical_scope_key
from app.market_collectors.normalize import safe_float, safe_int
from app.market_collectors.types import MarketQuery

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "quintoandar_search_v3.json"


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


def item(listing_id="894942131", **overrides):
    """A row shaped like the gateway's `hits.hits[]._source`."""
    value = {
        "id": listing_id,
        "salePrice": 3700000,
        "totalCost": 3704734,
        "iptuPlusCondominium": 4734,
        "area": 271,
        "address": "Rua Tomé de Souza",
        "regionName": "Savassi",
        "city": "Belo Horizonte",
        "neighbourhood": "Savassi",
        "type": "Apartamento",
        "forSale": True,
        "bedrooms": 4,
        "bathrooms": 3,
        "suites": 3,
        "parkingSpaces": 3,
    }
    value.update(overrides)
    return value


def payload(rows, total=None):
    hits = {"hits": [{"_id": str(row["id"]), "_source": row} for row in rows]}
    if total is not None:
        hits["total"] = total if isinstance(total, dict) else {"value": total, "relation": "eq"}
    return {"hits": hits}


def responder(monkeypatch, *responses, calls=None):
    stream = iter(responses)

    def request(*args, **kwargs):
        if calls is not None:
            calls.append(kwargs)
        return next(stream)

    monkeypatch.setattr("app.market_collectors.quintoandar.request", request)


def test_parses_the_real_captured_search_response(monkeypatch):
    responder(monkeypatch, Response(200, json.loads(FIXTURE.read_text())))
    result = collect(query(max_pages=1))

    assert result.success is True
    assert result.partial is False
    assert len(result.listings) == 5
    first = result.listings[0]
    assert first.listing_id == "116319001"
    assert first.url == "https://www.quintoandar.com.br/imovel/116319001/comprar"
    assert first.preco_total == 190000
    assert first.area_util_m2 == 18
    assert first.rua == "Avenida Bias Fortes"
    assert first.tipo_imovel == "APARTAMENTO"
    assert first.cidade == "Belo Horizonte"
    # The portal never exposes the street number on search results.
    assert all(listing.numero is None for listing in result.listings)


def test_requests_the_v3_contract_the_gateway_requires(monkeypatch):
    calls = []
    responder(monkeypatch, Response(200, payload([], total=0)), calls=calls)
    collect(query(max_pages=1))

    body = calls[0]["json_body"]
    assert calls[0]["headers"]["Content-Type"] == "application/json"
    assert body["slug"] == "savassi-belo-horizonte-mg-brasil"
    assert body["locationDescriptions"] == [{"description": "savassi-belo-horizonte-mg-brasil"}]
    assert body["filters"]["businessContext"] == "SALE"
    # Without an explicit field list the gateway answers with `id` alone.
    assert "salePrice" in body["fields"] and "area" in body["fields"]
    assert body["pagination"] == {"pageSize": PAGE_SIZE, "offset": 0}


def test_paginates_with_offsets_until_the_source_total_is_reached(monkeypatch):
    calls = []
    responder(
        monkeypatch,
        Response(200, payload([item(str(i)) for i in range(PAGE_SIZE)], total=PAGE_SIZE + 3)),
        Response(200, payload([item(f"b{i}") for i in range(3)], total=PAGE_SIZE + 3)),
        calls=calls,
    )
    result = collect(query(max_pages=5))

    assert result.success is True
    assert result.partial is False
    assert result.total == PAGE_SIZE + 3
    assert len(result.listings) == PAGE_SIZE + 3
    assert calls[0]["json_body"]["pagination"]["offset"] == 0
    assert calls[1]["json_body"]["pagination"]["offset"] == PAGE_SIZE


def test_scope_larger_than_the_gateway_cap_is_partial(monkeypatch):
    # The gateway rejects pageSize + offset above RESULT_CAP, so a bigger scope
    # can never be collected whole and must not deactivate what it cannot see.
    full = [item(str(i)) for i in range(PAGE_SIZE)]
    responder(
        monkeypatch,
        Response(200, payload(full, total=9000)),
        Response(200, payload([item(f"b{i}") for i in range(PAGE_SIZE)], total=9000)),
    )
    result = collect(query(max_pages=100))

    assert result.success is False
    assert result.partial is True
    assert result.error == "result_cap_reached"
    assert result.total == 9000
    assert len(result.listings) == RESULT_CAP


def test_never_requests_beyond_the_cap(monkeypatch):
    calls = []
    responder(
        monkeypatch,
        *[Response(200, payload([item(str(i)) for i in range(PAGE_SIZE)], total=9000))] * 2,
        calls=calls,
    )
    collect(query(max_pages=100))

    assert len(calls) == RESULT_CAP // PAGE_SIZE
    for call in calls:
        pagination = call["json_body"]["pagination"]
        assert pagination["pageSize"] + pagination["offset"] <= RESULT_CAP


def test_short_page_ends_the_collection_successfully(monkeypatch):
    responder(monkeypatch, Response(200, payload([item()], total=None)))
    result = collect(query(max_pages=100))

    assert result.success is True
    assert result.partial is False
    assert result.pages == 1


def test_preserves_known_zero_total(monkeypatch):
    responder(monkeypatch, Response(200, payload([], total=0)))
    result = collect(query(max_pages=1))

    assert result.success is True
    assert result.total == 0


def test_elasticsearch_gte_total_is_not_a_known_total(monkeypatch):
    rows = [item(str(i)) for i in range(PAGE_SIZE)]
    responder(
        monkeypatch,
        Response(200, payload(rows, total={"value": PAGE_SIZE, "relation": "gte"})),
        Response(200, payload([item("last")])),
    )
    result = collect(query(max_pages=2))

    assert result.total is None
    assert len(result.listings) == PAGE_SIZE + 1


def test_larger_earlier_total_is_not_replaced_by_smaller_later_total(monkeypatch):
    responder(
        monkeypatch,
        Response(200, payload([item(str(i)) for i in range(PAGE_SIZE)], total=900)),
        Response(200, payload([item("last")], total=50)),
    )
    result = collect(query(max_pages=2))

    assert result.total == 900


def test_ignores_repeated_ids_and_rows_without_a_sale_price(monkeypatch):
    rows = [
        item("qa-1"),
        item("qa-1", salePrice=800000),
        item("qa-no-price", salePrice=None),
        item("qa-rent", salePrice=None, rent=2500),
        item("qa-zero", salePrice=0),
    ]
    responder(monkeypatch, Response(200, payload(rows, total=5)))
    result = collect(query(max_pages=1))

    assert [listing.listing_id for listing in result.listings] == ["qa-1"]


def test_duplicate_ids_do_not_satisfy_the_source_total(monkeypatch):
    rows = [item(str(i)) for i in range(PAGE_SIZE - 1)] + [item("0")]
    responder(
        monkeypatch,
        Response(200, payload(rows, total=PAGE_SIZE)),
        Response(200, payload([], total=PAGE_SIZE)),
    )
    result = collect(query(max_pages=3))

    assert len(result.listings) == PAGE_SIZE - 1
    assert result.success is True


def test_applies_query_filters_to_the_house_specs_and_scope(monkeypatch):
    calls = []
    responder(monkeypatch, Response(200, payload([], total=0)), calls=calls)
    result = collect(query(tipo_imovel="casa", quartos=3, area_util_m2=120))

    specs = calls[0]["json_body"]["filters"]["houseSpecs"]
    assert specs["houseTypes"] == ["Casa"]
    assert specs["bedrooms"] == {"range": {"min": 3, "max": 3}}
    assert specs["area"] == {"range": {"min": 120, "max": 120}}
    assert '"tipo_imovel":"CASA"' in result.scope_key


def test_apartment_query_maps_to_the_portal_house_type(monkeypatch):
    calls = []
    responder(monkeypatch, Response(200, payload([], total=0)), calls=calls)
    collect(query(tipo_imovel="apartamento"))

    assert calls[0]["json_body"]["filters"]["houseSpecs"]["houseTypes"] == ["Apartamento"]


def test_city_wide_query_drops_the_neighborhood_from_the_slug(monkeypatch):
    calls = []
    responder(monkeypatch, Response(200, payload([], total=0)), calls=calls)
    collect(query(bairro=None))

    assert calls[0]["json_body"]["slug"] == "belo-horizonte-mg-brasil"


def test_unknown_type_is_not_a_valid_listing(monkeypatch):
    responder(monkeypatch, Response(200, payload([item(type="Palacio")], total=1)))
    assert collect(query(max_pages=1)).listings == []


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


def test_invalid_json_is_an_error(monkeypatch):
    responder(monkeypatch, Response(200, None, invalid_json=True))
    result = collect(query(max_pages=1))

    assert result.success is False
    assert result.error


def test_unexpected_payload_shapes_are_structural_errors(monkeypatch):
    for broken in ({"hits": ["not-an-item"]}, {"hits": {"hits": ["nope"]}}, {"search": {}}, []):
        responder(monkeypatch, Response(200, broken))
        assert collect(query(max_pages=1)).error == "invalid_payload_structure"


def test_raw_payload_does_not_keep_sensitive_contact_fields(monkeypatch):
    rows = [item(advertiserContact={"phones": ["5511999999999"], "email": "x@example.com"}, whatsappNumber="5511999999999")]
    responder(monkeypatch, Response(200, payload(rows, total=1)))
    raw = collect(query(max_pages=1)).listings[0].raw

    assert "advertiserContact" not in raw
    assert "whatsappNumber" not in raw


def test_rejects_invalid_positive_values(monkeypatch):
    responder(monkeypatch, Response(200, payload([item(area=-10, salePrice=0)], total=1)))
    assert collect(query(max_pages=1)).listings == []


def test_scope_key_is_stable():
    assert canonical_scope_key(query(), "quintoandar").startswith("quintoandar:")


def test_numeric_parser_preserves_decimal_and_brazilian_formats():
    assert safe_float("80.5") == 80.5
    assert safe_float("500000.00") == 500000.0
    assert safe_float("R$ 500.000,00") == 500000.0


def test_numeric_parser_rejects_lixo_and_ambiguous_separators():
    assert safe_float("abc123") is None
    assert safe_float("12abc34") is None
    assert safe_float("1e3") is None
    assert safe_float("1.234") is None


def test_rejects_invalid_positive_and_non_finite_values():
    assert safe_float("nan") is None
    assert safe_float("inf") is None
    assert safe_float("-1") is None
    assert safe_float("0", positive=True) is None


def test_safe_int_rejects_fractional_values():
    assert safe_int(2.9) is None
    assert safe_int("2.9") is None
    assert safe_int("2") == 2


def test_a_coordenada_do_portal_vira_lat_e_lon():
    # Sem coordenada esta fonte não alcança o cadastro imobiliário, e portanto
    # nem o tier de endereço nem o mapa: ela nunca publica número de rua.
    row = {
        "id": "123",
        "salePrice": 500000,
        "area": 80,
        "type": "Apartamento",
        "address": "Rua Tome de Souza",
        "city": "Belo Horizonte",
        "neighbourhood": "Savassi",
        "location": {"lat": -19.9380714, "lon": -43.9293474},
    }
    parsed = _parse(row, MarketQuery(cidade="Belo Horizonte", uf="MG"))
    assert parsed is not None
    assert parsed.lat == pytest.approx(-19.9380714)
    assert parsed.lon == pytest.approx(-43.9293474)
    assert parsed.coordinate_source == "QUINTOANDAR_LOCATION"


def test_sem_coordenada_o_anuncio_segue_valido():
    row = {
        "id": "123",
        "salePrice": 500000,
        "area": 80,
        "type": "Apartamento",
        "city": "Belo Horizonte",
        "neighbourhood": "Savassi",
    }
    parsed = _parse(row, MarketQuery(cidade="Belo Horizonte", uf="MG"))
    assert parsed is not None
    assert parsed.lat is None and parsed.coordinate_source is None


def test_location_malformada_nao_quebra():
    for ruim in ("", [], {"lat": "abc", "lon": None}, {"lon": -43.9}):
        row = {
            "id": "123",
            "salePrice": 500000,
            "area": 80,
            "type": "Apartamento",
            "city": "Belo Horizonte",
            "neighbourhood": "Savassi",
            "location": ruim,
        }
        parsed = _parse(row, MarketQuery(cidade="Belo Horizonte", uf="MG"))
        assert parsed is not None and parsed.lat is None
