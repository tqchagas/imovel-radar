from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from app.market_collectors.types import MarketQuery, NormalizedListing


def safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    elif "." in text and len(text.rsplit(".", 1)[1]) > 2:
        text = text.replace(".", "")
    text = re.sub(r"[^0-9.-]", "", text)
    try:
        return float(text) if text else None
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    number = safe_float(value)
    return int(number) if number is not None else None


def normalize_type(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if any(token in text for token in ("APART", "STUDIO", "KITNET", "COBERTURA", "FLAT", "LOFT")):
        return "APARTAMENTO"
    if "CASA" in text or "HOUSE" in text:
        return "CASA"
    return None


def query_type(value: Any) -> str | None:
    normalized = normalize_type(value)
    if value is not None and str(value).strip() and normalized is None:
        raise ValueError("unsupported_tipo_imovel")
    return normalized


def canonical_scope_key(query: MarketQuery, source: str) -> str:
    data = {
        "source": source.lower(),
        "uf": query.uf.strip().upper(),
        "cidade": query.cidade.strip(),
        "bairros": sorted([query.bairro.strip()] if query.bairro and query.bairro.strip() else []),
        "tipo_imovel": query.tipo_imovel,
        "quartos": query.quartos,
        "area_util_m2": query.area_util_m2,
    }
    return f"{source.lower()}:{json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}"


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
        area_util_m2=safe_float(values.get("area_util_m2")),
        preco_total=safe_float(values.get("preco_total")),
        lat=safe_float(values.get("lat")),
        lon=safe_float(values.get("lon")),
        coordinate_source=values.get("coordinate_source"),
        raw=data,
    )


def slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")
