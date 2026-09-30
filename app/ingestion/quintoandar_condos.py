"""Compatibility imports for the standalone QuintoAndar parser package."""

from quintoandar.condominiums import (
    SITEMAP_INDEX,
    CondoRow,
    condo_entries,
    parse_condo_page,
    sitemap_parts,
    slug_neighborhood,
)

SOURCE = "quintoandar"

__all__ = [
    "SITEMAP_INDEX", "SOURCE", "CondoRow", "condo_entries",
    "parse_condo_page", "sitemap_parts", "slug_neighborhood",
]
