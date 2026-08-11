import csv
import hashlib
import re
import unicodedata
from collections.abc import Iterator
from datetime import date, datetime
from io import TextIOWrapper
from typing import IO

from app.ingestion.base import ParsedTransaction

CITY = "belo_horizonte"
POSTAL_CODE_RE = re.compile(r"^\d{5}-\d{3}$")
STREET_NUMBER_RE = re.compile(r"^(.*\S)\s+(\d+[A-Za-z]?)$")


def _parse_decimal(raw: str) -> float | None:
    raw = raw.strip()
    if not raw or raw == "-":
        return None
    # Brazilian number format: dots as thousands separators and comma as
    # decimal separator, e.g. "280.000,00". Some exports replace the comma
    # with another dot, resulting in "280.000.00", so we try to detect the
    # decimal separator heuristically.
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        parts = raw.split(".")
        if len(parts) > 1 and parts[-1] and len(parts[-1]) <= 2:
            # Treat the last dot as the decimal separator.
            raw = "".join(parts[:-1]) + "." + parts[-1]
        else:
            raw = raw.replace(".", "")
    return float(raw)


def _parse_int(raw: str) -> int | None:
    raw = raw.strip()
    if not raw or raw == "-":
        return None
    return int(raw)


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw.strip(), "%d/%m/%Y").date()


def _split_address(
    raw_address: str,
) -> tuple[str, str | None, str | None, str | None]:
    tokens = [t.strip() for t in raw_address.split(" - ")]
    street_tokens = tokens[:1]
    postal_code = None
    for i, token in enumerate(tokens):
        if POSTAL_CODE_RE.match(token):
            street_tokens = tokens[: i - 1] if i >= 2 else tokens[:1]
            postal_code = token
            break

    street_and_number = street_tokens[0] if street_tokens else raw_address
    complement = " - ".join(street_tokens[1:]) or None

    match = STREET_NUMBER_RE.match(street_and_number)
    if match:
        street, street_number = match.group(1), match.group(2)
    else:
        street, street_number = street_and_number, None

    return street, street_number, complement, postal_code


def _row_hash(row: dict[str, str]) -> str:
    canonical = ";".join(row[key] for key in sorted(row))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_FIELD_ALIASES: dict[str, list[str]] = {
    "Endereco Completo": ["Endereco Completo", "Endereco"],
    "Bairro": ["Bairro"],
    "Ano de Construcao (Unidade)": ["Ano de Construcao (Unidade)"],
    "Area Terreno Total": ["Area Terreno Total"],
    "Area Construida Adquirida": ["Area Construida Adquirida"],
    "Area Adquirida (Unidades Somadas)": ["Area Adquirida (Unidades Somadas)"],
    "Padrao Acabamento (Unidade)": ["Padrao Acabamento (Unidade)"],
    "Fracao Ideal Adquirida": ["Fracao Ideal Adquirida"],
    "Tipo Construtivo Preponderante": ["Tipo Construtivo Preponderante"],
    "Descrição Tipo Ocupacao (Unidade)": ["Descrição Tipo Ocupacao (Unidade)"],
    "Valor Declarado": ["Valor Declarado"],
    "Valor Base Calculo": ["Valor Base Calculo"],
    "Zona Uso ITBI": ["Zona Uso ITBI", "Zona Uso"],
    "Data Quitacao": ["Data Quitacao", "Data Quitacao Transacao"],
}


def _normalize_key(name: str) -> str:
    # Fold case, accents and punctuation so header variations across ITBI
    # exports ("Zona Uso ITBI", "ZONA DE USO ITBI", "Zona Uso Itbi") still map
    # to the same canonical field.
    stripped = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    stripped = re.sub(r"[^0-9a-z]+", " ", stripped.lower())
    return stripped.strip()


def _get_field(row: dict[str, str], canonical: str) -> str:
    for alias in _FIELD_ALIASES[canonical]:
        if alias in row:
            return row[alias]

    normalized_row = {_normalize_key(key): value for key, value in row.items()}
    for alias in _FIELD_ALIASES[canonical]:
        value = normalized_row.get(_normalize_key(alias))
        if value is not None:
            return value

    raise KeyError(
        f"Coluna '{canonical}' nao encontrada. Colunas do arquivo: "
        f"{', '.join(sorted(k for k in row if k))}"
    )


def parse_row(row: dict[str, str]) -> ParsedTransaction:
    raw_address = _get_field(row, "Endereco Completo").strip()
    street, street_number, complement, postal_code = _split_address(raw_address)
    return ParsedTransaction(
        city=CITY,
        source_row_hash=_row_hash(row),
        raw_address=raw_address,
        street=street,
        street_number=street_number,
        complement=complement,
        postal_code=postal_code,
        neighborhood=_get_field(row, "Bairro").strip(),
        construction_year=_parse_int(_get_field(row, "Ano de Construcao (Unidade)")),
        land_area=_parse_decimal(_get_field(row, "Area Terreno Total")),
        built_area_acquired=_parse_decimal(_get_field(row, "Area Construida Adquirida")),
        acquired_area_total=_parse_decimal(_get_field(row, "Area Adquirida (Unidades Somadas)")),
        finish_standard=_get_field(row, "Padrao Acabamento (Unidade)").strip() or None,
        acquired_fraction=_parse_decimal(_get_field(row, "Fracao Ideal Adquirida")),
        construction_type=_get_field(row, "Tipo Construtivo Preponderante").strip() or None,
        occupation_type=_get_field(row, "Descrição Tipo Ocupacao (Unidade)").strip() or None,
        declared_value=_parse_decimal(_get_field(row, "Valor Declarado")) or 0.0,
        calc_base_value=_parse_decimal(_get_field(row, "Valor Base Calculo")) or 0.0,
        zoning=_get_field(row, "Zona Uso ITBI").strip() or None,
        settlement_date=_parse_date(_get_field(row, "Data Quitacao")),
    )


def _normalize_headers(fieldnames: list[str] | None) -> list[str] | None:
    if fieldnames is None:
        return None
    return [name.strip() for name in fieldnames]


def parse_stream(file: TextIOWrapper) -> Iterator[ParsedTransaction]:
    reader = csv.DictReader(file, delimiter=";")
    reader.fieldnames = _normalize_headers(reader.fieldnames)
    for row in reader:
        yield parse_row(row)


def parse_file(path: str) -> Iterator[ParsedTransaction]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        yield from parse_stream(f)
