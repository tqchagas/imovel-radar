"""Light normalization for ITBI complement strings (unit identifiers)."""

from __future__ import annotations

import re
import unicodedata

# Longest-first alternation so APTO/APT win over AP, etc.
_PREFIX_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"^(APARTAMENTO|APTO|APT\.?|AP)(?=\s|\d|$)", re.IGNORECASE),
        "APT",
    ),
    (
        re.compile(r"^(SALA|SL\.?)(?=\s|\d|$)", re.IGNORECASE),
        "SALA",
    ),
    (
        re.compile(r"^(LOJA|LJ\.?)(?=\s|\d|$)", re.IGNORECASE),
        "LJ",
    ),
    (
        re.compile(r"^(GARAGEM|VAGA|GAR\.?|GA)(?=\s|\d|$)", re.IGNORECASE),
        "GA",
    ),
    (
        re.compile(r"^(COBERTURA|COB\.?)(?=\s|\d|$)", re.IGNORECASE),
        "COB",
    ),
    (
        re.compile(r"^(CASA|CS\.?)(?=\s|\d|$)", re.IGNORECASE),
        "CS",
    ),
]


def normalize_street_key(value: str | None) -> str:
    """Uppercase/trim only — no logradouro expansion (product decision)."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip().upper())


def normalize_complement(raw: str | None) -> str | None:
    """Canonical complement for grouping unit history.

    - strips accents, uppercases, collapses whitespace
    - maps common type prefixes to a short canonical token (APT, LJ, …)
    - preserves type so APT 1201 does not merge with LJ 1201
    """
    if raw is None:
        return None

    stripped = unicodedata.normalize("NFKD", raw)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    stripped = stripped.upper().strip()
    stripped = stripped.replace(" - ", " ")
    stripped = re.sub(r"\s+", " ", stripped)
    if not stripped:
        return None

    for pattern, token in _PREFIX_RULES:
        match = pattern.match(stripped)
        if match:
            rest = stripped[match.end() :].strip(" .-")
            rest = re.sub(r"\s+", " ", rest)
            return f"{token} {rest}".strip() if rest else token

    return stripped
