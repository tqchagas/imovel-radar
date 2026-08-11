from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.properties import router as properties_router
from app.api.routes.stats import router as stats_router
from app.api.routes.transactions import router as transactions_router

app = FastAPI(title="ImovelRadar API")
app.include_router(transactions_router)
app.include_router(properties_router)
app.include_router(stats_router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Screen name -> static file. Query strings stay in the URL (deep links).
PAGES = {
    "/busca": "busca.html",
    "/imovel": "property.html",
    "/bairro": "bairro.html",
    "/comparar": "comparar.html",
    "/enviar": "enviar.html",
    "/estilo": "estilo.html",
}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root(request: Request) -> RedirectResponse:
    # Preserve query string so deep links like /?street=X&street_number=Y work.
    target = "/static/index.html"
    if request.url.query:
        target = f"{target}?{request.url.query}"
    return RedirectResponse(url=target)


def _page(filename: str):
    def serve() -> FileResponse:
        return FileResponse(static_dir / filename)

    return serve


for path, filename in PAGES.items():
    app.get(path, include_in_schema=False)(_page(filename))
