from app.domain.complement import normalize_complement, normalize_street_key


def test_normalize_complement_maps_apt_variants() -> None:
    assert normalize_complement("APT 1201") == "APT 1201"
    assert normalize_complement("APTO 1201") == "APT 1201"
    assert normalize_complement("AP 1201") == "APT 1201"
    assert normalize_complement("apto 1201") == "APT 1201"
    assert normalize_complement("  apt   1201  ") == "APT 1201"


def test_normalize_complement_keeps_type_separate() -> None:
    assert normalize_complement("APT 1201") != normalize_complement("LJ 1201")
    assert normalize_complement("LJ 12") == "LJ 12"
    assert normalize_complement("LOJA 12") == "LJ 12"
    assert normalize_complement("GARAGEM 01") == "GA 01"


def test_normalize_complement_multi_token() -> None:
    assert normalize_complement("APT 402 BLOCO 2") == "APT 402 BLOCO 2"
    assert normalize_complement("APT 402 - BLOCO 2") == "APT 402 BLOCO 2"


def test_normalize_complement_empty() -> None:
    assert normalize_complement(None) is None
    assert normalize_complement("") is None
    assert normalize_complement("   ") is None


def test_normalize_street_key() -> None:
    assert normalize_street_key("  ave augusto  ") == "AVE AUGUSTO"
    assert normalize_street_key(None) == ""
