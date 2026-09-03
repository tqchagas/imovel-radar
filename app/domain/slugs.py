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


def address_key(value: str | None) -> str | None:
    """Accent- and case-insensitive key used to match addresses across sources."""
    if value is None or not str(value).strip():
        return None
    decomposed = unicodedata.normalize("NFKD", str(value))
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_") or None


# O cartório e o cadastro da prefeitura abreviam o tipo do logradouro em três
# letras; o portal escreve por extenso. "AVE AUGUSTO DE LIMA" e "Avenida
# Augusto de Lima" são o mesmo endereço e produziam chaves diferentes, o que
# derrubava todo anúncio de avenida do tier de rua para o de bairro — 1.705
# anúncios ativos em Belo Horizonte, nenhum deles alcançando a rua. Praça,
# rodovia, alameda e estrada tinham o mesmo destino em menor escala.
#
# A forma canônica é a por extenso: é a que os portais já gravam, então
# expandir mantém as chaves de anúncio como estão e conserta só o outro lado.
STREET_TYPE_CANONICAL = {
    "ave": "avenida",
    "av": "avenida",
    "r": "rua",
    "pca": "praca",
    "pc": "praca",
    "rod": "rodovia",
    "ala": "alameda",
    "al": "alameda",
    "est": "estrada",
    "bec": "beco",
    "trv": "travessa",
    "tv": "travessa",
}


def street_key(value: str | None) -> str | None:
    """`address_key` com o tipo do logradouro expandido para a forma por extenso.

    Use esta, e não `address_key`, sempre que uma rua de uma fonte precisar
    encontrar a mesma rua de outra.
    """
    key = address_key(value)
    if key is None:
        return None
    tipo, _, resto = key.partition("_")
    canonico = STREET_TYPE_CANONICAL.get(tipo)
    if canonico is None or not resto:
        return key
    return f"{canonico}_{resto}"
