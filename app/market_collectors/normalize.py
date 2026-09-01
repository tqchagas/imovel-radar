from __future__ import annotations

import json
import math
import numbers
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

from app.market_collectors.types import MarketQuery, NormalizedListing


def safe_float(value: Any, *, positive: bool = False, allow_negative: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, numbers.Real):
        result = float(value)
        return result if math.isfinite(result) and (allow_negative or result >= 0) and (not positive or result > 0) else None
    text = str(value).strip()
    currency = text.startswith("R$")
    if text.startswith("R$"):
        text = text[2:].strip()
    if not text or re.search(r"\s", text):
        return None
    sign = r"[+-]?" if allow_negative else r"\+?"
    patterns = (
        rf"{sign}\d+",
        rf"{sign}\d+\.\d{{1,2}}",
        rf"{sign}\d+,\d{{1,2}}",
        rf"{sign}\d{{1,3}}(?:\.\d{{3}})+,\d{{1,2}}",
    )
    if currency:
        patterns += (rf"{sign}\d{{1,3}}(?:\.\d{{3}})+",)
    if not any(re.fullmatch(pattern, text) for pattern in patterns):
        return None
    grouped_currency = currency and re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+", text)
    normalized = text.replace(".", "").replace(",", ".") if "," in text or grouped_currency else text
    try:
        result = float(normalized)
    except ValueError:
        return None
    return result if math.isfinite(result) and (allow_negative or result >= 0) and (not positive or result > 0) else None


def safe_int(value: Any) -> int | None:
    number = safe_float(value)
    return int(number) if number is not None and number.is_integer() else None


def normalize_type(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if any(token in text for token in ("APART", "STUDIO", "KITNET", "COBERTURA", "FLAT", "LOFT")):
        return "APARTAMENTO"
    if "CASA" in text or "HOUSE" in text or text == "HOME":
        return "CASA"
    return None


def query_type(value: Any) -> str | None:
    normalized = normalize_type(value)
    if value is not None and str(value).strip() and normalized is None:
        raise ValueError("unsupported_tipo_imovel")
    return normalized


def canonical_scope_key(query: MarketQuery, source: str) -> str:
    bairros = list(query.bairros or ((query.bairro,) if query.bairro else ()))
    filtros = dict(query.filtros)
    for key in ("tipo_imovel", "quartos", "area_util_m2"):
        value = getattr(query, key)
        if value is not None:
            filtros[key] = value
    data = {
        "source": source.strip().lower(),
        "uf": query.uf.strip().upper(),
        "cidade": query.cidade.strip(),
        "bairros": sorted({bairro.strip() for bairro in bairros if bairro and bairro.strip()}, key=str.casefold),
        "filtros": filtros,
    }
    return f"{data['source']}:{json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}"


def listing(source: str, query: MarketQuery, data: dict[str, Any], **values: Any) -> NormalizedListing:
    return NormalizedListing(
        source=source,
        listing_id=str(values["listing_id"]),
        url=str(values["url"]),
        uf=str(values.get("uf") or query.uf),
        cidade=str(values.get("cidade") or query.cidade),
        bairro=values.get("bairro") or query.bairro,
        rua=values.get("rua"),
        numero=str(values["numero"]) if values.get("numero") is not None else None,
        tipo_imovel=normalize_type(values.get("tipo_imovel")),
        quartos=safe_int(values.get("quartos")),
        bathrooms=safe_int(values.get("bathrooms")),
        suites=safe_int(values.get("suites")),
        parking_spaces=safe_int(values.get("parking_spaces")),
        area_util_m2=safe_float(values.get("area_util_m2"), positive=True),
        preco_total=safe_float(values.get("preco_total"), positive=True),
        lat=safe_float(values.get("lat"), allow_negative=True),
        lon=safe_float(values.get("lon"), allow_negative=True),
        coordinate_source=values.get("coordinate_source"),
        raw=sanitize_raw(data),
    )


def slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def is_portal_url(source: str, url: str) -> bool:
    allowed = {
        "quintoandar": {"quintoandar.com.br", "www.quintoandar.com.br"},
        "vivareal": {"vivareal.com.br", "www.vivareal.com.br"},
    }.get(source, set())
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname in allowed
        and parsed.username is None
        and parsed.password is None
        and (port is None or port == 443)
    )


def sanitize_raw(value: Any) -> Any:
    if isinstance(value, dict):
        sensitive = ("contact", "phone", "whatsapp", "email", "advertiser")
        return {
            key: sanitize_raw(item)
            for key, item in value.items()
            if not any(token in str(key).lower() for token in sensitive)
            and not _looks_sensitive_value(item)
        }
    if isinstance(value, list):
        return [sanitize_raw(item) for item in value if not _looks_sensitive_value(item)]
    return value


def _looks_sensitive_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", text):
        return True
    digits = re.sub(r"\D", "", text)
    return len(digits) in range(10, 14) and len(digits) == len(re.sub(r"[+().\-\s]", "", text))
