from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.curiosities import router as curiosities_router
from app.api.routes.properties import router as properties_router
from app.api.routes.stats import router as stats_router
from app.api.routes.transactions import router as transactions_router
from app.domain.slugs import neighborhood_path, property_path

app = FastAPI(title="ImovelRadar API")
app.include_router(transactions_router)
app.include_router(properties_router)
app.include_router(stats_router)
app.include_router(curiosities_router)

static_dir = Path(__file__).resolve().parent / "static"

# Screen name -> static file. Query strings stay in the URL (deep links).
PAGES = {
    "/": "index.html",
    "/busca": "busca.html",
    "/imovel": "property.html",
    "/bairro": "bairro.html",
    "/curiosidades": "curiosidades.html",
    "/comparar": "comparar.html",
    "/enviar": "enviar.html",
    "/estilo": "estilo.html",
}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


def _page(filename: str):
    def serve() -> FileResponse:
        return FileResponse(static_dir / filename)

    return serve


def _legacy_html_redirect(target: str):
    def go(request: Request) -> RedirectResponse:
        url = target
        if request.url.query:
            url = f"{target}?{request.url.query}"
        return RedirectResponse(url=url, status_code=301)

    return go


# Query-string detail URLs 301 to the slug path.
CUSTOM_PAGES = {"/bairro", "/imovel"}

for path, filename in PAGES.items():
    if path not in CUSTOM_PAGES:
        app.get(path, include_in_schema=False)(_page(filename))
    # Old /static/*.html bookmarks keep working after the friendly-URL cutover.
    app.get(f"/static/{filename}", include_in_schema=False)(_legacy_html_redirect(path))


@app.get("/bairro", include_in_schema=False, response_model=None)
def bairro_page(request: Request) -> FileResponse | RedirectResponse:
    city = request.query_params.get("city")
    neighborhood = request.query_params.get("neighborhood")
    if city and neighborhood:
        months_raw = request.query_params.get("months")
        months = int(months_raw) if months_raw and months_raw.isdigit() else None
        return RedirectResponse(
            url=neighborhood_path(city, neighborhood, months),
            status_code=301,
        )
    return FileResponse(static_dir / "bairro.html")


@app.get("/bairro/{city_slug}/{neighborhood_slug}/", include_in_schema=False)
def bairro_detail_page(city_slug: str, neighborhood_slug: str) -> FileResponse:
    return FileResponse(static_dir / "bairro.html")


@app.get("/imovel", include_in_schema=False, response_model=None)
def imovel_page(request: Request) -> FileResponse | RedirectResponse:
    city = request.query_params.get("city")
    street = request.query_params.get("street")
    if (
        city
        and street
        and not request.query_params.get("transaction_id")
        and not request.query_params.get("from_transaction")
    ):
        return RedirectResponse(
            url=property_path(
                city,
                street,
                request.query_params.get("street_number"),
                request.query_params.get("complement"),
            ),
            status_code=301,
        )
    return FileResponse(static_dir / "property.html")


@app.get(
    "/imovel/{city_slug}/{street_slug}/{street_number}/{complement_slug}/",
    include_in_schema=False,
)
def imovel_unit_page(
    city_slug: str,
    street_slug: str,
    street_number: str,
    complement_slug: str,
) -> FileResponse:
    return FileResponse(static_dir / "property.html")


@app.get("/imovel/{city_slug}/{street_slug}/{street_number}/", include_in_schema=False)
def imovel_number_page(
    city_slug: str, street_slug: str, street_number: str
) -> FileResponse:
    return FileResponse(static_dir / "property.html")


@app.get("/imovel/{city_slug}/{street_slug}/", include_in_schema=False)
def imovel_street_page(city_slug: str, street_slug: str) -> FileResponse:
    return FileResponse(static_dir / "property.html")


app.mount("/static", StaticFiles(directory=static_dir), name="static")
