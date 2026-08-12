from app.domain.slugs import neighborhood_path, property_path, slugify


def test_slugify_city_snake_case() -> None:
    assert slugify("belo_horizonte") == "belo-horizonte"


def test_slugify_neighborhood_uppercase() -> None:
    assert slugify("BELVEDERE") == "belvedere"


def test_slugify_neighborhood_with_spaces() -> None:
    assert slugify("SAO CRISTOVAO") == "sao-cristovao"
    assert slugify("CIDADE NOVA") == "cidade-nova"


def test_slugify_strips_accents() -> None:
    assert slugify("SÃO CRISTÓVÃO") == "sao-cristovao"


def test_neighborhood_path() -> None:
    assert (
        neighborhood_path("belo_horizonte", "BELVEDERE")
        == "/bairro/belo-horizonte/belvedere/"
    )


def test_neighborhood_path_keeps_non_default_months() -> None:
    assert (
        neighborhood_path("belo_horizonte", "BELVEDERE", months=24)
        == "/bairro/belo-horizonte/belvedere/?months=24"
    )


def test_neighborhood_path_omits_default_months() -> None:
    assert (
        neighborhood_path("belo_horizonte", "BELVEDERE", months=12)
        == "/bairro/belo-horizonte/belvedere/"
    )


def test_property_path_with_complement() -> None:
    assert (
        property_path(
            "belo_horizonte",
            "RUA DOUTOR VIRGILIO UCHOA",
            "414",
            "APT",
        )
        == "/imovel/belo-horizonte/rua-doutor-virgilio-uchoa/414/apt/"
    )


def test_property_path_without_complement() -> None:
    assert (
        property_path("belo_horizonte", "RUA CASA", "10")
        == "/imovel/belo-horizonte/rua-casa/10/"
    )


def test_property_path_street_only() -> None:
    assert (
        property_path("belo_horizonte", "RUA CASA")
        == "/imovel/belo-horizonte/rua-casa/"
    )


def test_property_path_complement_without_number() -> None:
    assert (
        property_path("belo_horizonte", "RUA CASA", None, "APT 1201")
        == "/imovel/belo-horizonte/rua-casa/-/apt-1201/"
    )
