import re
import unicodedata


def slugify(value: str) -> str:
    """Lowercase ASCII slug: spaces/underscores become hyphens, accents drop."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_value.lower()
    hyphenated = re.sub(r"[_\s]+", "-", lowered)
    cleaned = re.sub(r"[^a-z0-9-]", "", hyphenated)
    collapsed = re.sub(r"-{2,}", "-", cleaned)
    return collapsed.strip("-")


def neighborhood_path(
    city: str, neighborhood: str, months: int | None = None
) -> str:
    path = f"/bairro/{slugify(city)}/{slugify(neighborhood)}/"
    if months is not None and months != 12:
        return f"{path}?months={months}"
    return path


def street_path(city: str, street: str) -> str:
    return f"/rua/{slugify(city)}/{slugify(street)}/"


def stored_city(city: str) -> str:
    """Cities are stored snake_case; URL slugs use hyphens."""
    return city.replace("-", "_")


def property_path(
    city: str,
    street: str,
    street_number: str | None = None,
    complement: str | None = None,
) -> str:
    parts = [slugify(city), slugify(street)]
    number = slugify(street_number) if street_number else ""
    unit = slugify(complement) if complement else ""
    if number:
        parts.append(number)
        if unit:
            parts.append(unit)
    elif unit:
        parts.extend(["-", unit])
    return "/imovel/" + "/".join(parts) + "/"
