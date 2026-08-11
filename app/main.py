from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.properties import router as properties_router
from app.api.routes.transactions import router as transactions_router

app = FastAPI(title="ImovelRadar API")
app.include_router(transactions_router)
app.include_router(properties_router)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/static/index.html")


@app.get("/imovel")
def property_page() -> FileResponse:
    """Shareable property history page (canonical query params in the URL)."""
    return FileResponse(static_dir / "property.html")
