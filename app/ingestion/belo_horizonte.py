import csv
import hashlib
import re
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
    if not raw:
        return None
    return float(raw.replace(",", "."))


def _parse_int(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
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


def parse_row(row: dict[str, str]) -> ParsedTransaction:
    raw_address = row["Endereco Completo"].strip()
    street, street_number, complement, postal_code = _split_address(raw_address)
    return ParsedTransaction(
        city=CITY,
        source_row_hash=_row_hash(row),
        raw_address=raw_address,
        street=street,
        street_number=street_number,
        complement=complement,
        postal_code=postal_code,
        neighborhood=row["Bairro"].strip(),
        construction_year=_parse_int(row["Ano de Construcao (Unidade)"]),
        land_area=_parse_decimal(row["Area Terreno Total"]),
        built_area_acquired=_parse_decimal(row["Area Construida Adquirida"]),
        acquired_area_total=_parse_decimal(row["Area Adquirida (Unidades Somadas)"]),
        finish_standard=row["Padrao Acabamento (Unidade)"].strip() or None,
        acquired_fraction=_parse_decimal(row["Fracao Ideal Adquirida"]),
        construction_type=row["Tipo Construtivo Preponderante"].strip() or None,
        occupation_type=row["Descrição Tipo Ocupacao (Unidade)"].strip() or None,
        declared_value=_parse_decimal(row["Valor Declarado"]) or 0.0,
        calc_base_value=_parse_decimal(row["Valor Base Calculo"]) or 0.0,
        zoning=row["Zona Uso ITBI"].strip() or None,
        settlement_date=_parse_date(row["Data Quitacao"]),
    )


def parse_stream(file: TextIOWrapper) -> Iterator[ParsedTransaction]:
    reader = csv.DictReader(file, delimiter=";")
    for row in reader:
        yield parse_row(row)


def parse_file(path: str) -> Iterator[ParsedTransaction]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        yield from parse_stream(f)
