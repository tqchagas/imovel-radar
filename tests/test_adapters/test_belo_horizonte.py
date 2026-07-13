from datetime import date

from app.ingestion.belo_horizonte import CITY, parse_file, parse_row

SAMPLE_ROW = {
    "Endereco Completo": (
        "AVE AUGUSTO DE LIMA 134 - APT 1201 - CENTRO - 30190-001 - "
        "BELO HORIZONTE - MG"
    ),
    "Bairro": "CENTRO",
    "Ano de Construcao (Unidade)": "1965",
    "Area Terreno Total": "1080",
    "Area Construida Adquirida": "47,25",
    "Area Adquirida (Unidades Somadas)": "47,25",
    "Padrao Acabamento (Unidade)": "P3",
    "Fracao Ideal Adquirida": "0,00333",
    "Tipo Construtivo Preponderante": "AP",
    "Descrição Tipo Ocupacao (Unidade)": "RESIDENCIAL",
    "Valor Declarado": "270000",
    "Valor Base Calculo": "270000",
    "Zona Uso ITBI": "ZHIP",
    "Data Quitacao": "01/06/2026",
}


def test_parse_row_extracts_street_line_and_postal_code() -> None:
    parsed = parse_row(SAMPLE_ROW)

    assert parsed.city == CITY
    assert parsed.street_line == "AVE AUGUSTO DE LIMA 134 - APT 1201"
    assert parsed.postal_code == "30190-001"
    assert parsed.neighborhood == "CENTRO"


def test_parse_row_normalizes_numbers_and_dates() -> None:
    parsed = parse_row(SAMPLE_ROW)

    assert parsed.construction_year == 1965
    assert parsed.land_area == 1080.0
    assert parsed.built_area_acquired == 47.25
    assert parsed.acquired_fraction == 0.00333
    assert parsed.declared_value == 270000.0
    assert parsed.settlement_date == date(2026, 6, 1)


def test_parse_row_is_deterministic_for_dedup_hash() -> None:
    first = parse_row(SAMPLE_ROW)
    second = parse_row(SAMPLE_ROW)
    assert first.source_row_hash == second.source_row_hash


def test_parse_file_reads_all_rows() -> None:
    rows = list(parse_file("tests/fixtures/belo_horizonte_sample.csv"))
    assert len(rows) == 2
    assert rows[0].neighborhood == "CENTRO"
    assert rows[1].neighborhood == "CIDADE NOVA"
