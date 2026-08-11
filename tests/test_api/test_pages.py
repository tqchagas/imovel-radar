import pytest
from fastapi.testclient import TestClient

from app.main import PAGES, app

client = TestClient(app)


def test_root_redirects_to_static_index() -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/static/index.html"


def test_static_index_is_served() -> None:
    response = client.get("/static/index.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ImovelRadar" in response.text


@pytest.mark.parametrize("path", sorted(PAGES))
def test_screen_routes_serve_html(path: str) -> None:
    response = client.get(path)
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
        "/static/comparar.js",
        "/static/enviar.js",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
