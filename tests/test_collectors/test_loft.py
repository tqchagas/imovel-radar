import json
from pathlib import Path

from app.market_collectors.loft import PAGE_SIZE, RESULT_CAP, collect
from app.market_collectors.normalize import canonical_scope_key
from app.market_collectors.types import MarketQuery

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "loft_search_v4.json"


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


def item(listing_id="dmh1ioiz", **overrides):
    """A row shaped like `listings[].listing`."""
    value = {
        "id": listing_id,
        "price": 480000,
        "area": 40,
        "homeType": "apartment",
        "usageType": "residential",
        "propertyType": "default",
        "bedrooms": 1,
        "restrooms": 1,
        "suits": 0,
        "parkingSpots": 1,
        "address": {
            "streetName": "Rua Antônio de Albuquerque",
            "streetFullName": "Rua Antônio de Albuquerque",
            "number": None,
            "postalCode": None,
            "neighborhood": "Savassi",
            "city": "Belo Horizonte",
            "state": "MG",
            "lat": "-19.9390581",
            "lng": "-43.9338435",
        },
    }
    value.update(overrides)
    return value


def payload(rows, total_cards=None, total_pages=1):
    return {
        "listings": [{"listing": row} for row in rows],
        "pagination": {
            "page": 1,
            "hitsPerPage": PAGE_SIZE,
            "totalListings": (total_cards or len(rows)) * 2,
            "totalCards": total_cards if total_cards is not None else len(rows),
            "totalPages": total_pages,
        },
    }


def responder(monkeypatch, *responses, calls=None):
    stream = iter(responses)

    def request(*args, **kwargs):
        if calls is not None:
            calls.append(kwargs)
        return next(stream)

    monkeypatch.setattr("app.market_collectors.loft.request", request)


def test_parses_the_real_captured_search_response(monkeypatch):
    responder(monkeypatch, Response(200, json.loads(FIXTURE.read_text())))
    result = collect(query(max_pages=1))

    assert len(result.listings) == 5
    first = result.listings[0]
    assert first.listing_id == "dmh1ioiz"
    assert first.url == "https://loft.com.br/imovel/dmh1ioiz"
    assert first.preco_total == 480000
    assert first.area_util_m2 == 40
    assert first.rua == "Rua Antônio de Albuquerque"
    assert first.bairro == "Savassi"
    assert first.tipo_imovel == "APARTAMENTO"
    # The search payload never carries the street number.
    assert all(listing.numero is None for listing in result.listings)


def test_parses_coordinates_that_safe_float_would_reject(monkeypatch):
    # Loft sends lat/lng as strings with seven decimals.
    responder(monkeypatch, Response(200, payload([item()])))
    listing = collect(query(max_pages=1)).listings[0]

    assert listing.lat == -19.9390581
    assert listing.lon == -43.9338435
    assert listing.coordinate_source == "LOFT_GEOLOC"


def test_sends_the_contract_the_gateway_requires(monkeypatch):
    calls = []
    responder(monkeypatch, Response(200, payload([], total_cards=0)), calls=calls)
    collect(query(max_pages=1))

    headers, body = calls[0]["headers"], calls[0]["json_body"]
    # Origin is the only header that separates 200 from 403.
    assert headers["Origin"] == "https://loft.com.br"
    assert len(headers["loftUserId"]) == 36
    assert body["transactionType"] == ["for_sale"]
    assert body["cities"] == ["belo horizonte, mg"]
    # The bare neighborhood name matches nothing; only the qualified form works.
    assert body["neighborhood"] == ["Savassi, Belo Horizonte, MG"]
    assert body["searchVariant"] == "v3"
    assert body["hitsPerPage"] == PAGE_SIZE


def test_each_request_uses_a_fresh_user_id(monkeypatch):
    calls = []
    responder(
        monkeypatch,
        Response(200, payload([item(str(i)) for i in range(PAGE_SIZE)], total_cards=999, total_pages=3)),
        Response(200, payload([item("b")], total_cards=999, total_pages=3)),
        Response(200, payload([item("c")], total_cards=999, total_pages=3)),
        calls=calls,
    )
    collect(query(max_pages=3))

    ids = [call["headers"]["loftUserId"] for call in calls]
    assert len(set(ids)) == len(ids)


def test_city_wide_query_omits_the_neighborhood(monkeypatch):
    calls = []
    responder(monkeypatch, Response(200, payload([], total_cards=0)), calls=calls)
    collect(query(bairro=None, max_pages=1))

    assert "neighborhood" not in calls[0]["json_body"]


def test_pagination_follows_total_pages_not_row_count(monkeypatch):
    # Cards collapse after the page is sliced, so a short page does not mean
    # the scope is exhausted.
    calls = []
    responder(
        monkeypatch,
        Response(200, payload([item("a1"), item("a2")], total_cards=600, total_pages=3)),
        Response(200, payload([item("b1")], total_cards=600, total_pages=3)),
        Response(200, payload([item("c1")], total_cards=600, total_pages=3)),
        calls=calls,
    )
    result = collect(query(max_pages=10))

    assert len(calls) == 3
    assert result.success is True
    assert result.partial is False
    assert [call["json_body"]["page"] for call in calls] == [1, 2, 3]
    assert len(result.listings) == 4


def test_stops_at_the_last_page(monkeypatch):
    responder(monkeypatch, Response(200, payload([item()], total_cards=1, total_pages=1)))
    result = collect(query(max_pages=10))

    assert result.success is True
    assert result.pages == 1


def test_scope_larger_than_the_gateway_cap_is_partial(monkeypatch):
    pages = RESULT_CAP // PAGE_SIZE
    responder(
        monkeypatch,
        *[
            Response(200, payload([item(f"p{page}-{i}") for i in range(PAGE_SIZE)], total_cards=50000, total_pages=9999))
            for page in range(pages)
        ],
    )
    result = collect(query(max_pages=1000))

    assert result.success is False
    assert result.partial is True
    assert result.error == "result_cap_reached"
    assert len(result.listings) == RESULT_CAP


def test_applies_filters_to_the_request_and_scope(monkeypatch):
    calls = []
    responder(monkeypatch, Response(200, payload([], total_cards=0)), calls=calls)
    result = collect(query(tipo_imovel="casa", quartos=3, area_util_m2=120))

    body = calls[0]["json_body"]
    assert body["homeType"] == ["house"]
    # bedrooms is a scalar and needs the exact-match flag; an array answers 400.
    assert body["bedrooms"] == 3
    assert body["exactMatchForNumericFields"] is True
    assert body["areaMin"] == 120 and body["areaMax"] == 120
    assert '"tipo_imovel":"CASA"' in result.scope_key


def test_apartment_query_maps_to_the_portal_home_type(monkeypatch):
    calls = []
    responder(monkeypatch, Response(200, payload([], total_cards=0)), calls=calls)
    collect(query(tipo_imovel="apartamento"))

    assert calls[0]["json_body"]["homeType"] == ["apartment"]


def test_non_residential_and_untyped_rows_are_skipped(monkeypatch):
    rows = [
        item("comercial", usageType="commercial"),
        item("terreno", homeType="land_lot"),
        item("lote-comercial", homeType="commercial_land_lot", usageType="commercial"),
        item("valida"),
    ]
    responder(monkeypatch, Response(200, payload(rows, total_cards=4)))
    result = collect(query(max_pages=1))

    assert [listing.listing_id for listing in result.listings] == ["valida"]


def test_rows_without_a_usable_price_are_skipped(monkeypatch):
    rows = [item("sem-preco", price=None), item("preco-zero", price=0), item("ok")]
    responder(monkeypatch, Response(200, payload(rows, total_cards=3)))
    result = collect(query(max_pages=1))

    assert [listing.listing_id for listing in result.listings] == ["ok"]


def test_listings_without_area_are_kept(monkeypatch):
    # Roughly 40% of the catalogue has no area; the row is still a real listing.
    responder(monkeypatch, Response(200, payload([item(area=None)], total_cards=1)))
    listing = collect(query(max_pages=1)).listings[0]

    assert listing.area_util_m2 is None
    assert listing.preco_total == 480000


def test_ignores_repeated_ids(monkeypatch):
    responder(monkeypatch, Response(200, payload([item("x"), item("x")], total_cards=2)))
    assert [l.listing_id for l in collect(query(max_pages=1)).listings] == ["x"]


def test_unknown_query_type_is_rejected(monkeypatch):
    responder(monkeypatch, Response(200, payload([], total_cards=0)))
    assert collect(query(tipo_imovel="palacio")).error == "unsupported_tipo_imovel"


def test_http_failure_on_the_first_page_is_partial(monkeypatch):
    responder(monkeypatch, Response(403, {}))
    result = collect(query())

    assert result.success is False
    assert result.partial is True
    assert result.pages == 0
    assert result.error == "http_403"


def test_invalid_json_is_an_error(monkeypatch):
    responder(monkeypatch, Response(200, None, invalid_json=True))
    result = collect(query(max_pages=1))

    assert result.success is False
    assert result.error


def test_unexpected_payload_shapes_are_structural_errors(monkeypatch):
    for broken in ({"listings": "nope"}, {"listings": ["not-a-row"]}, {}, []):
        responder(monkeypatch, Response(200, broken))
        assert collect(query(max_pages=1)).error == "invalid_payload_structure"


def test_raw_payload_does_not_keep_sensitive_contact_fields(monkeypatch):
    row = item(agencyName="Imobiliária X", whatsappNumber="5511999999999", contactEmail="x@example.com")
    responder(monkeypatch, Response(200, payload([row], total_cards=1)))
    raw = collect(query(max_pages=1)).listings[0].raw

    assert "whatsappNumber" not in raw
    assert "contactEmail" not in raw


def test_scope_key_is_stable():
    assert canonical_scope_key(query(), "loft").startswith("loft:")


def test_portal_padding_is_stripped_from_names(monkeypatch):
    # VivaReal hands back "Santo Antônio " with a trailing space, and that name
    # is later fed back as an exact-match filter: one stray space is enough for
    # a portal to answer 200 with nothing.
    row = item(address={
        "streetName": "  Rua   Antônio de Albuquerque ",
        "neighborhood": "Santo Antônio ",
        "city": " Belo Horizonte",
        "number": None,
        "lat": "-19.9",
        "lng": "-43.9",
    })
    responder(monkeypatch, Response(200, payload([row], total_cards=1)))
    listing = collect(query(max_pages=1)).listings[0]

    assert listing.bairro == "Santo Antônio"
    assert listing.rua == "Rua Antônio de Albuquerque"
    assert listing.cidade == "Belo Horizonte"


# --- área vinda da descrição --------------------------------------------------


def parsed(monkeypatch, **row_overrides):
    """Coleta um anúncio só e devolve o normalizado."""
    responder(monkeypatch, Response(200, payload([item(**row_overrides)])))
    result = collect(query(max_pages=1))
    return result.listings[0] if result.listings else None


def test_the_portal_area_is_kept_and_marked_as_such(monkeypatch):
    listing = parsed(monkeypatch, area=40)

    assert listing.area_util_m2 == 40.0
    assert listing.area_origem == "portal"


def test_a_missing_area_is_recovered_from_the_description(monkeypatch):
    # 31% dos anúncios do Loft vêm sem `area`; em 60% deles o m² está no texto.
    listing = parsed(
        monkeypatch, area=None,
        description="Apartamento com área privativa de 98m², 3 quartos.",
    )

    assert listing.area_util_m2 == 98.0
    # Marcada, porque o texto é ambíguo: validando contra os anúncios que
    # publicam área, o texto discorda em ~13% dos casos — quase sempre por
    # nomear uma parte (interna, terraço) em vez do total. Quem consome decide
    # se confia.
    assert listing.area_origem == "descricao"


def test_an_implausible_area_in_the_text_is_ignored(monkeypatch):
    listing = parsed(monkeypatch, area=None, description="Condomínio com 2000m² de lazer.")

    assert listing.area_util_m2 is None
    assert listing.area_origem is None


def test_a_description_without_any_measure_leaves_the_area_empty(monkeypatch):
    listing = parsed(monkeypatch, area=None, description="Excelente oportunidade, 3 quartos.")

    assert listing.area_util_m2 is None
