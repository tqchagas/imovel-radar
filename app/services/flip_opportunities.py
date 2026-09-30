"""Collect and calculate the conservative Belo Horizonte flip garimpo."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.flip_opportunities import (
    ALLOWED_NEIGHBORHOODS,
    COMPLEMENTARY_NEIGHBORHOODS,
    PRIORITY_NEIGHBORHOODS,
    FlipCandidate,
    FlipComparable,
    FlipOpportunity,
    area_band,
    calculate_opportunity,
)
from app.domain.opportunities import ListingInput, unit_fingerprint
from app.domain.slugs import address_key
from app.market_collectors import MarketQuery
from app.market_collectors.normalize import is_portal_url
from app.core.http_client import request
from app.models.market_comparable import MarketComparable
from app.services.market_refresh import collect_and_refresh

SOURCES = ("loft", "quintoandar", "vivareal")
PROPERTY_TYPES = ("APARTAMENTO", "CASA")
CITY = "Belo Horizonte"
UF = "MG"
VERIFY_TTL = timedelta(hours=24)
PAGE_VERIFICATION_LIMIT = 100
SOURCE_DOMAINS = {
    "loft": "loft.com.br",
    "quintoandar": "quintoandar.com.br",
    "vivareal": "vivareal.com.br",
}
DISQUALIFY = re.compile(
    r"leil[aã]o|venda judicial|judicial|arremata[cç][aã]o|adjudica[cç][aã]o|"
    r"aliena[cç][aã]o fiduci[aá]ria|portal de im[oó]veis caixa|im[oó]vel da caixa|"
    r"venda por banco|im[oó]vel retomado pelo banco|venda banc[aá]ria",
    re.IGNORECASE,
)
UNAVAILABLE = re.compile(
    r"im[oó]vel (?:n[aã]o est[aá] mais dispon[ií]vel|indispon[ií]vel)|"
    r"an[uú]ncio expirado|p[aá]gina n[aã]o encontrada|access denied|captcha|"
    r"temporarily unavailable",
    re.IGNORECASE,
)


class _ListingPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.title: list[str] = []
        self.meta: list[str] = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag == "meta" and attributes.get("property") in {
            "og:title",
            "og:description",
            "description",
        }:
            self.meta.append(attributes.get("content", ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        if not self._skip:
            self.text.append(data)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None) if value.tzinfo else value


def _page_mentions_area(text: str, area: float) -> bool:
    values = {f"{area:g}", f"{area:.1f}".rstrip("0").rstrip("."), f"{area:.2f}".rstrip("0").rstrip(".")}
    values |= {value.replace(".", ",") for value in tuple(values)}
    return any(
        re.search(rf"(?<!\d){re.escape(value)}\s*(?:m²|m2|metros quadrados)", text, re.I)
        for value in values
    )


def _page_mentions_price(text: str, price: float) -> bool:
    integer = int(round(price))
    localized = f"{integer:,}".replace(",", ".")
    candidates = {str(integer), localized}
    return any(
        re.search(rf"R\s*\$\s*{re.escape(value)}(?:,00)?\b", text, re.I)
        for value in candidates
    )


def _verify_page(row: MarketComparable) -> tuple[str, str | None]:
    """Read the canonical individual page; never bypass a portal block."""
    if row.source not in SOURCE_DOMAINS or not row.url or not is_portal_url(row.source, row.url):
        return "rejected", "url_individual_invalida"
    try:
        response = request(
            "GET",
            row.url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "ImovelRadar/1.0 (public property listing validation)",
            },
            timeout=15,
        )
    except Exception as error:  # noqa: BLE001 - unavailable pages are ineligible
        return "rejected", f"falha_de_acesso:{type(error).__name__}"

    status_code = int(response.status_code)
    if not 200 <= status_code < 300:
        return "rejected", f"http_{status_code}"
    final = urlparse(response.url)
    allowed_domain = SOURCE_DOMAINS[row.source]
    final_host = (final.hostname or "").lower()
    if final_host not in {allowed_domain, f"www.{allowed_domain}"}:
        return "rejected", "redirecionado_fora_do_portal"
    if str(row.listing_id) not in final.path:
        return "rejected", "redirecionado_para_pagina_generica"

    page = _ListingPage()
    try:
        page.feed(response.text)
    except Exception:  # noqa: BLE001 - malformed HTML is not confirmation
        return "rejected", "html_invalido"
    visible = " ".join(" ".join(page.text).split())
    title_and_meta = " ".join(" ".join(page.title + page.meta).split())
    if len(visible) < 120 or UNAVAILABLE.search(title_and_meta) or UNAVAILABLE.search(visible[:1200]):
        return "rejected", "pagina_bloqueada_generica_ou_inativa"
    if DISQUALIFY.search(title_and_meta):
        return "rejected", "nao_e_venda_convencional"

    area = float(row.area_util_m2) if row.area_util_m2 is not None else None
    price = float(row.preco_total) if row.preco_total is not None else None
    vagas = row.parking_spaces
    if row.area_origem == "descricao":
        return "rejected", "area_nao_publicada_pelo_portal"
    if area is None or price is None or vagas is None or vagas < 1:
        return "rejected", "area_preco_ou_vaga_ausente"
    if not _page_mentions_area(visible, area):
        return "rejected", "area_nao_confirmada_na_pagina"
    if not _page_mentions_price(visible, price):
        return "rejected", "preco_nao_confirmado_na_pagina"
    if not re.search(rf"(?<!\d){vagas}\s+(?:vaga|vagas|garagem|garagens)\b", visible, re.I):
        return "rejected", "vaga_nao_confirmada_na_pagina"
    bairro = (row.bairro or "").strip()
    if bairro and address_key(bairro) not in address_key(visible):
        return "rejected", "bairro_nao_confirmado_na_pagina"
    # Keep optional details only when the individual page confirms them.
    if row.bedrooms is not None and not re.search(
        rf"(?<!\d){row.bedrooms}\s+(?:quarto|quartos|dormit[oó]rio|dormit[oó]rios)\b",
        visible,
        re.I,
    ):
        row.bedrooms = None
    if row.rua and address_key(row.rua) not in address_key(visible):
        row.rua = None
    if row.condominium_value is not None and not _page_mentions_price(
        visible, float(row.condominium_value)
    ):
        row.condominium_value = None
    return "verified", None


def _candidate(row: MarketComparable) -> FlipCandidate:
    return FlipCandidate(
        source=row.source,
        listing_id=row.listing_id,
        url=row.url or "",
        bairro=row.bairro,
        rua=row.rua,
        tipo_imovel=row.tipo_imovel,
        area_m2=float(row.area_util_m2) if row.area_util_m2 is not None else None,
        bedrooms=row.bedrooms,
        parking_spaces=row.parking_spaces,
        condominium=float(row.condominium_value) if row.condominium_value is not None else None,
        price=float(row.preco_total) if row.preco_total is not None else None,
        fingerprint=_row_fingerprint(row),
        page_verified_at=row.page_verification_checked_at,
        last_seen_at=row.last_seen_at,
    )


def _comparables(rows: list[MarketComparable]) -> list[FlipComparable]:
    return [
        FlipComparable(
            listing_id=row.listing_id,
            fingerprint=_row_fingerprint(row),
            bairro=row.bairro,
            tipo_imovel=row.tipo_imovel,
            area_m2=float(row.area_util_m2) if row.area_util_m2 is not None else None,
            price=float(row.preco_total) if row.preco_total is not None else None,
        )
        for row in rows
    ]


def _same_unit_key(row: MarketComparable) -> str:
    return _row_fingerprint(row) or f"{row.source}:{row.listing_id}"


def _row_fingerprint(row: MarketComparable) -> str | None:
    """Build the same cross-portal unit key before generic scoring runs."""
    return row.unidade_fingerprint or unit_fingerprint(
        ListingInput(
            source=row.source,
            listing_id=row.listing_id,
            tipo_imovel=row.tipo_imovel,
            area_util_m2=float(row.area_util_m2) if row.area_util_m2 is not None else None,
            preco_total=float(row.preco_total) if row.preco_total is not None else None,
            bairro=row.bairro,
            rua=row.rua,
        )
    )


def _preferred(rows: list[MarketComparable]) -> MarketComparable:
    source_priority = {"quintoandar": 0, "vivareal": 1, "loft": 2}
    return max(
        rows,
        key=lambda row: (
            sum(value is not None for value in (
                row.bairro, row.rua, row.area_util_m2, row.bedrooms,
                row.parking_spaces, row.condominium_value, row.preco_total,
            )),
            row.last_seen_at,
            -source_priority.get(row.source, 9),
        ),
    )


def _deduplicate(rows: list[MarketComparable]) -> list[MarketComparable]:
    groups: dict[str, list[MarketComparable]] = {}
    for row in rows:
        groups.setdefault(_same_unit_key(row), []).append(row)
    return [_preferred(group) for group in groups.values()]


def list_flip_opportunities(db: Session, *, city: str = CITY) -> list[FlipOpportunity]:
    city_key = address_key(city)
    listings = db.scalars(
        select(MarketComparable)
        .where(
            MarketComparable.ativo.is_(True),
            MarketComparable.cidade_normalizada == city_key,
            MarketComparable.bairro_normalizado.in_(ALLOWED_NEIGHBORHOODS),
        )
        .order_by(MarketComparable.id)
    ).all()
    comparables = _comparables(
        [
            row for row in listings
            if row.source == "quintoandar"
            and row.page_verification_status == "verified"
            and _naive_utc(row.page_verification_checked_at) is not None
            and _naive_utc(row.page_verification_checked_at) >= _naive_utc(row.last_seen_at)
            and row.tipo_imovel in {"APARTAMENTO", "CASA"}
            and row.preco_total is not None
            and row.area_util_m2 is not None
            and area_band(float(row.area_util_m2)) is not None
        ]
    )
    candidate_results: list[tuple[MarketComparable, FlipOpportunity]] = []
    for row in listings:
        if row.source not in SOURCES:
            continue
        candidate = _candidate(row)
        checked = _naive_utc(row.page_verification_checked_at)
        last_seen = _naive_utc(row.last_seen_at)
        if (
            row.page_verification_status != "verified"
            or checked is None
            or last_seen is None
            or checked < last_seen
        ):
            continue
        result = calculate_opportunity(candidate, comparables, city=city)
        if result is not None:
            candidate_results.append((row, result))

    unique: dict[str, list[tuple[MarketComparable, FlipOpportunity]]] = {}
    for pair in candidate_results:
        unique.setdefault(_same_unit_key(pair[0]), []).append(pair)
    outputs: list[FlipOpportunity] = []
    for group in unique.values():
        row = _preferred([pair[0] for pair in group])
        result = calculate_opportunity(_candidate(row), comparables, city=city)
        if result is not None:
            outputs.append(result)
    return sorted(
        (result for result in outputs if result is not None),
        key=lambda result: (
            result.gap_pct,
            result.comparable_count,
            result.candidate.price or 0,
        ),
        reverse=True,
    )


def refresh_flip_garimpo(
    db: Session,
    *,
    neighborhoods: tuple[str, ...] | None = None,
    sources: tuple[str, ...] = SOURCES,
    city: str = CITY,
    uf: str = UF,
    max_pages: int = 100,
) -> dict[str, int | str | list[dict[str, object]]]:
    """Refresh only the defined flip areas, verify detail pages, and summarize."""
    bairros = neighborhoods or PRIORITY_NEIGHBORHOODS + COMPLEMENTARY_NEIGHBORHOODS
    collections: list[dict[str, object]] = []
    for tipo in PROPERTY_TYPES:
        for bairro in bairros:
            for source in sources:
                try:
                    result = collect_and_refresh(
                        db,
                        MarketQuery(
                            uf=uf,
                            cidade=city,
                            bairro=bairro.replace("_", " "),
                            source=source,
                            tipo_imovel=tipo,
                            max_pages=max_pages,
                            filtros={"tipo_imovel": tipo},
                        ),
                    )
                    collections.append({"source": source, "bairro": bairro, "tipo": tipo, **result})
                except Exception as error:  # noqa: BLE001 - isolate one failed scope
                    db.rollback()
                    collections.append({
                        "source": source,
                        "bairro": bairro,
                        "tipo": tipo,
                        "status": "failed",
                        "error": str(error)[:240],
                    })

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    eligible_rows = db.scalars(
        select(MarketComparable).where(
            MarketComparable.ativo.is_(True),
            MarketComparable.cidade_normalizada == address_key(city),
            MarketComparable.bairro_normalizado.in_(ALLOWED_NEIGHBORHOODS),
            MarketComparable.source.in_(SOURCES),
            MarketComparable.tipo_imovel.in_(PROPERTY_TYPES),
            MarketComparable.preco_total > 0,
            MarketComparable.parking_spaces >= 1,
            MarketComparable.area_util_m2 >= 30,
            MarketComparable.area_util_m2 <= 350,
            MarketComparable.url.is_not(None),
        ).order_by(MarketComparable.id)
    ).all()

    checked = verified = rejected = cached = 0
    due_rows: list[MarketComparable] = []
    for row in eligible_rows:
        if row.source != "quintoandar" and float(row.preco_total) > 700000:
            continue
        previous = _naive_utc(row.page_verification_checked_at)
        if previous is not None and now - previous < VERIFY_TTL:
            cached += 1
            continue
        due_rows.append(row)

    # Validate a bounded batch on each scheduled run. Check QuintoAndar first
    # because its confirmed pages form the reference medians; unverified rows
    # precede pages already checked in an earlier cycle so coverage advances.
    due_rows.sort(
        key=lambda row: (
            row.page_verification_checked_at is not None,
            row.source != "quintoandar",
            _naive_utc(row.page_verification_checked_at) or datetime.min,
            row.bairro_normalizado or "",
            row.tipo_imovel or "",
            float(row.area_util_m2 or 0),
            row.id,
        )
    )
    rows_to_check = due_rows[:PAGE_VERIFICATION_LIMIT]
    for index, row in enumerate(rows_to_check, start=1):
        status, reason = _verify_page(row)
        row.page_verification_status = status
        row.page_verification_checked_at = now
        row.page_verification_error = reason
        checked += 1
        if status == "verified":
            verified += 1
        else:
            rejected += 1
        if index % 25 == 0:
            db.commit()
    db.commit()

    results = list_flip_opportunities(db, city=city)
    return {
        "status": "ok",
        "collections": collections,
        "page_checks": checked,
        "page_verified": verified,
        "page_rejected": rejected,
        "page_check_cached": cached,
        "page_check_deferred": len(due_rows) - len(rows_to_check),
        "eligible_opportunities": len(results),
        "opportunities": [
            {
                "source": result.candidate.source,
                "listing_id": result.candidate.listing_id,
                "status": result.status,
                "gap_pct": round(result.gap_pct, 4),
                "comparables": result.comparable_count,
            }
            for result in results
        ],
    }
