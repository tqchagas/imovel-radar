from collections import defaultdict
from datetime import date
from urllib.parse import urljoin

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.domain.complement import normalize_complement
from app.domain.slugs import neighborhood_path, property_path, slugify, street_path
from app.models.transaction import Transaction
from app.seo.eligibility import property_quality
from app.seo.curiosities import curiosity_context
from app.seo.pages import neighborhood_context, street_context
from app.seo.sitemap import sitemap_index_xml, sitemap_xml

router = APIRouter(include_in_schema=False)


def _absolute(path: str) -> str:
    return urljoin(settings.public_base_url.rstrip("/") + "/", path.lstrip("/"))


def _distinct_pairs(db: Session, first, second) -> list[tuple[str, str]]:
    rows = db.execute(select(first, second).distinct()).all()
    return [(left, right) for left, right in rows if left and right]


def neighborhood_urls(db: Session) -> list[tuple[str, date | None]]:
    urls: list[tuple[str, date | None]] = []
    for city, neighborhood in _distinct_pairs(db, Transaction.city, Transaction.neighborhood):
        context = neighborhood_context(db, city.replace("_", "-"), slugify(neighborhood))
        if context and context["quality"].indexable:
            last = db.scalar(
                select(func.max(Transaction.settlement_date)).where(
                    Transaction.city == city, Transaction.neighborhood == neighborhood
                )
            )
            urls.append((_absolute(neighborhood_path(city, neighborhood)), last))
    return urls


def street_urls(db: Session) -> list[tuple[str, date | None]]:
    urls: list[tuple[str, date | None]] = []
    for city, street in _distinct_pairs(db, Transaction.city, Transaction.street):
        context = street_context(db, city.replace("_", "-"), slugify(street))
        if context and context["quality"].indexable:
            last = db.scalar(
                select(func.max(Transaction.settlement_date)).where(
                    Transaction.city == city, Transaction.street == street
                )
            )
            urls.append((_absolute(street_path(city, street)), last))
    return urls


def property_urls(db: Session) -> list[tuple[str, date | None]]:
    groups: dict[tuple[str, str, str | None, str | None], list[Transaction]] = defaultdict(list)
    for tx in db.scalars(select(Transaction)).yield_per(10_000):
        groups[(tx.city, slugify(tx.street), tx.street_number, normalize_complement(tx.complement))].append(tx)

    urls: list[tuple[str, date | None]] = []
    for (city, street_slug, street_number, complement), rows in groups.items():
        quality = property_quality(len(rows))
        if not quality.indexable:
            continue
        sample = rows[0]
        urls.append((
            _absolute(property_path(city, sample.street, street_number, complement)),
            max(row.settlement_date for row in rows),
        ))
    return urls


def curiosity_urls(db: Session) -> list[tuple[str, date | None]]:
    last = db.scalar(select(func.max(Transaction.settlement_date)))
    urls: list[tuple[str, date | None]] = []
    for city in db.scalars(select(Transaction.city).distinct()).all():
        city_slug = city.replace("_", "-")
        context = curiosity_context(db, city_slug)
        if context is None:
            continue
        urls.append((_absolute(f"/curiosidades/{city_slug}/"), last))
        urls.extend((_absolute(item.url), last) for item in context["insights"])
    return urls


@router.get("/sitemap.xml")
def sitemap_index() -> Response:
    root = sitemap_index_xml(
        [
            _absolute("/sitemap-bairros.xml"),
            _absolute("/sitemap-ruas.xml"),
            _absolute("/sitemap-imoveis.xml"),
            _absolute("/sitemap-curiosidades.xml"),
        ]
    )
    return Response(root, media_type="application/xml")


@router.get("/sitemap-bairros.xml")
def neighborhood_sitemap(db: Session = Depends(get_db)) -> Response:
    return Response(sitemap_xml(neighborhood_urls(db)), media_type="application/xml")


@router.get("/sitemap-ruas.xml")
def street_sitemap(db: Session = Depends(get_db)) -> Response:
    return Response(sitemap_xml(street_urls(db)), media_type="application/xml")


@router.get("/sitemap-imoveis.xml")
def property_sitemap(db: Session = Depends(get_db)) -> Response:
    return Response(sitemap_xml(property_urls(db)), media_type="application/xml")


@router.get("/sitemap-curiosidades.xml")
def curiosity_sitemap(db: Session = Depends(get_db)) -> Response:
    return Response(sitemap_xml(curiosity_urls(db)), media_type="application/xml")
