from fastapi.testclient import TestClient

from app.main import app

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


def test_static_assets_are_served() -> None:
    for path in ["/static/styles.css", "/static/app.js"]:
        response = client.get(path)
        assert response.status_code == 200, path
