import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes.curiosities import router as curiosities_router
from app.api.routes.curiosities import warm_default_curiosities
from app.api.routes.flips import router as flips_router
from app.api.routes.auctions import router as auctions_router
from app.api.routes.opportunities import router as opportunities_router
from app.api.routes.properties import router as properties_router
from app.api.routes.stats import router as stats_router
from app.api.routes.sitemap import router as sitemap_router
from app.api.routes.transactions import router as transactions_router
from app.core.config import settings
from app.domain.slugs import neighborhood_path, property_path
from app.db.session import SessionLocal, get_db
from app.seo.curiosities import curiosity_context
from app.seo.pages import neighborhood_context, property_context, street_context

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.warm_curiosities_on_startup:
        db = SessionLocal()
        try:
            logger.info("Warming curiosities cache")
            warm_default_curiosities(db)
            logger.info("Curiosities cache ready")
        except Exception:
            logger.exception("Curiosities warmup failed; the first request will retry")
        finally:
            db.close()
    yield


app = FastAPI(title="ImovelRadar API", lifespan=lifespan)
app.include_router(transactions_router)
app.include_router(properties_router)
app.include_router(stats_router)
app.include_router(curiosities_router)
app.include_router(opportunities_router)
app.include_router(auctions_router)
app.include_router(flips_router)
app.include_router(sitemap_router)

static_dir = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

# Screen name -> static file. Query strings stay in the URL (deep links).
PAGES = {
    "/": "index.html",
    "/busca": "busca.html",
    "/imovel": "property.html",
    "/bairro": "bairro.html",
    "/curiosidades": "curiosidades.html",
    "/comparar": "comparar.html",
    "/enviar": "enviar.html",
    # Opportunities stay out of SEO: the page itself is noindex.
    "/oportunidades": "oportunidades.html",
    # Imóveis de leilão são anotação particular do dono: noindex, fora do
    # sitemap e fora da navegação pública, como /enviar.
    "/leilao": "leilao.html",
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


@app.get("/bairro/{city_slug}/{neighborhood_slug}/", include_in_schema=False, response_model=None)
def bairro_detail_page(
    request: Request,
    city_slug: str,
    neighborhood_slug: str,
    months: int = 12,
    db: Session = Depends(get_db),
) -> FileResponse | object:
    try:
        context = neighborhood_context(db, city_slug, neighborhood_slug, months)
    except SQLAlchemyError:
        return FileResponse(static_dir / "bairro.html")
    if context is None:
        return FileResponse(static_dir / "bairro.html", status_code=404)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="neighborhood.html", context=context)


@app.get("/rua/{city_slug}/{street_slug}/", include_in_schema=False, response_model=None)
def rua_detail_page(
    request: Request,
    city_slug: str,
    street_slug: str,
    months: int = 12,
    db: Session = Depends(get_db),
) -> FileResponse | object:
    try:
        context = street_context(db, city_slug, street_slug, months)
    except SQLAlchemyError:
        return FileResponse(static_dir / "bairro.html")
    if context is None:
        return FileResponse(static_dir / "bairro.html", status_code=404)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="street.html", context=context)


@app.get("/curiosidades/{city_slug}/", include_in_schema=False, response_model=None)
@app.get("/curiosidades/{city_slug}/{kind}/", include_in_schema=False, response_model=None)
def curiosities_page(
    request: Request,
    city_slug: str,
    kind: str | None = None,
    db: Session = Depends(get_db),
) -> FileResponse | object:
    try:
        context = curiosity_context(db, city_slug, kind)
    except SQLAlchemyError:
        return FileResponse(static_dir / "curiosidades.html")
    if context is None:
        return FileResponse(static_dir / "curiosidades.html", status_code=404)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="curiosities.html", context=context)


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
    response_model=None,
)
def imovel_unit_page(
    request: Request,
    city_slug: str,
    street_slug: str,
    street_number: str,
    complement_slug: str,
    db: Session = Depends(get_db),
) -> FileResponse | object:
    try:
        context = property_context(db, city_slug, street_slug, street_number, complement_slug)
    except SQLAlchemyError:
        return FileResponse(static_dir / "property.html")
    if context is None:
        return FileResponse(static_dir / "property.html", status_code=404)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="property.html", context=context)


@app.get("/imovel/{city_slug}/{street_slug}/{street_number}/", include_in_schema=False, response_model=None)
def imovel_number_page(
    request: Request,
    city_slug: str,
    street_slug: str,
    street_number: str,
    db: Session = Depends(get_db),
) -> FileResponse | object:
    try:
        context = property_context(db, city_slug, street_slug, street_number, None)
    except SQLAlchemyError:
        return FileResponse(static_dir / "property.html")
    if context is None:
        return FileResponse(static_dir / "property.html", status_code=404)
    context["request"] = request
    return templates.TemplateResponse(request=request, name="property.html", context=context)


@app.get("/imovel/{city_slug}/{street_slug}/", include_in_schema=False)
def imovel_street_page(city_slug: str, street_slug: str) -> FileResponse:
    return FileResponse(static_dir / "property.html")


app.mount("/static", StaticFiles(directory=static_dir), name="static")
