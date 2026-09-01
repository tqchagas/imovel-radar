from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import PAGES, app

client = TestClient(app)


def test_root_serves_index() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ImovelRadar" in response.text


def test_root_keeps_legacy_query_string() -> None:
    response = client.get("/?street=Amazonas", follow_redirects=False)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.parametrize("path,filename", sorted(PAGES.items()))
def test_legacy_html_paths_redirect_to_friendly_urls(path: str, filename: str) -> None:
    response = client.get(f"/static/{filename}", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == path


def test_legacy_index_redirect_preserves_query() -> None:
    response = client.get("/static/index.html?street=Amazonas", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/?street=Amazonas"


@pytest.mark.parametrize("path", sorted(PAGES))
def test_screen_routes_serve_html(path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_bairro_detail_path_serves_html() -> None:
    response = client.get("/bairro/belo-horizonte/belvedere/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Bairros" in response.text


def test_bairro_detail_path_without_slash_redirects() -> None:
    response = client.get("/bairro/belo-horizonte/belvedere", follow_redirects=False)
    assert response.status_code in {301, 307}
    assert response.headers["location"].endswith("/bairro/belo-horizonte/belvedere/")


def test_legacy_bairro_query_redirects_to_slug_path() -> None:
    response = client.get(
        "/bairro",
        params={"city": "belo_horizonte", "neighborhood": "BELVEDERE"},
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == "/bairro/belo-horizonte/belvedere/"


def test_legacy_bairro_query_preserves_months() -> None:
    response = client.get(
        "/bairro",
        params={
            "city": "belo_horizonte",
            "neighborhood": "BELVEDERE",
            "months": "24",
        },
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == "/bairro/belo-horizonte/belvedere/?months=24"


def test_imovel_detail_path_serves_html() -> None:
    response = client.get("/imovel/belo-horizonte/rua-doutor-virgilio-uchoa/414/apt/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Linha do tempo" in response.text


def test_imovel_detail_path_without_slash_redirects() -> None:
    response = client.get(
        "/imovel/belo-horizonte/rua-doutor-virgilio-uchoa/414/apt",
        follow_redirects=False,
    )
    assert response.status_code in {301, 307}
    assert response.headers["location"].endswith(
        "/imovel/belo-horizonte/rua-doutor-virgilio-uchoa/414/apt/"
    )


def test_legacy_imovel_query_redirects_to_slug_path() -> None:
    response = client.get(
        "/imovel",
        params={
            "city": "belo_horizonte",
            "street": "RUA DOUTOR VIRGILIO UCHOA",
            "street_number": "414",
            "complement": "APT",
        },
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert (
        response.headers["location"]
        == "/imovel/belo-horizonte/rua-doutor-virgilio-uchoa/414/apt/"
    )


def test_imovel_transaction_query_is_not_redirected() -> None:
    response = client.get(
        "/imovel",
        params={"transaction_id": "12"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_static_assets_are_served() -> None:
    for path in [
        "/static/styles.css",
        "/static/common.js",
        "/static/home.js",
        "/static/busca.js",
        "/static/property.js",
        "/static/bairro.js",
        "/static/curiosidades.js",
        "/static/comparar.js",
        "/static/enviar.js",
        "/static/oportunidades.js",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path


def test_curiosities_interactive_page_has_a_primary_exploration_cta() -> None:
    response = client.get("/curiosidades")

    assert response.status_code == 200
    assert 'id="explore-city"' in response.text


def test_opportunities_page_is_served_and_kept_out_of_seo() -> None:
    response = client.get("/oportunidades")

    assert response.status_code == 200
    assert "Oportunidades de compra" in response.text
    assert 'name="robots" content="noindex, nofollow"' in response.text


def test_opportunities_page_is_absent_from_the_sitemap() -> None:
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert "/oportunidades" not in response.text


def test_seo_surfaces_never_read_listings() -> None:
    # SEO pages and sitemaps are built from ITBI rows only; listings stay private.
    seo_sources = list(Path("app/seo").glob("*.py")) + [Path("app/api/routes/sitemap.py")]

    for source in seo_sources:
        assert "MarketComparable" not in source.read_text(), source
