from datetime import date
from io import StringIO

from app.ingestion.belo_horizonte import CITY, parse_file, parse_row, parse_stream

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


def test_parse_row_extracts_street_number_complement_and_postal_code() -> None:
    parsed = parse_row(SAMPLE_ROW)

    assert parsed.city == CITY
    assert parsed.street == "AVE AUGUSTO DE LIMA"
    assert parsed.street_number == "134"
    assert parsed.complement == "APT 1201"
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


def test_parse_row_handles_multi_word_complement() -> None:
    row = dict(SAMPLE_ROW)
    row["Endereco Completo"] = (
        "AVE MEM DE SA 160 - APT 402 BLOCO 2 - SANTA EFIGENIA - "
        "30260-270 - BELO HORIZONTE - MG"
    )

    parsed = parse_row(row)

    assert parsed.street == "AVE MEM DE SA"
    assert parsed.street_number == "160"
    assert parsed.complement == "APT 402 BLOCO 2"


def test_parse_file_reads_all_rows() -> None:
    rows = list(parse_file("tests/fixtures/belo_horizonte_sample.csv"))
    assert len(rows) == 2
    assert rows[0].neighborhood == "CENTRO"
    assert rows[1].neighborhood == "CIDADE NOVA"


CSV_WITH_SPACED_HEADERS = """Endereco Completo;Bairro;Ano de Construcao (Unidade);Area Terreno Total;Area Construida Adquirida;Area Adquirida (Unidades Somadas);Padrao Acabamento (Unidade);Fracao Ideal Adquirida;Tipo Construtivo Preponderante;Descrição Tipo Ocupacao (Unidade); Valor Declarado ; Valor Base Calculo ;Zona Uso ITBI;Data Quitacao
RUA A 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG;CENTRO;2000;100;60;60;P3;1;AP;RESIDENCIAL;300000;300000;ZA;01/06/2026"""


def test_parse_stream_handles_headers_with_leading_or_trailing_spaces() -> None:
    rows = list(parse_stream(StringIO(CSV_WITH_SPACED_HEADERS)))
    assert len(rows) == 1
    assert rows[0].declared_value == 300000.0
    assert rows[0].calc_base_value == 300000.0


def test_parse_decimal_handles_brazilian_number_format() -> None:
    from app.ingestion.belo_horizonte import _parse_decimal, _parse_int

    assert _parse_decimal("280.000,00") == 280000.00
    assert _parse_decimal("280000,00") == 280000.00
    assert _parse_decimal("280000.00") == 280000.00
    assert _parse_decimal("280.000") == 280000.0
    assert _parse_decimal("280000") == 280000.0
    assert _parse_decimal("-") is None
    assert _parse_decimal("") is None
    assert _parse_int("-") is None
    assert _parse_int("") is None


CSV_FEV_2026_HEADERS = """Endereco ;Bairro;Ano de Construcao (Unidade); Area Terreno Total ; Area Construida Adquirida ; Area Adquirida (Unidades Somadas) ;Padrao Acabamento (Unidade);Fracao Ideal Adquirida;Tipo Construtivo Preponderante;Descrição Tipo Ocupacao (Unidade); Valor Declarado ; Valor Base Calculo ;Zona Uso ITBI;Data Quitacao
RUA A 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG;CENTRO;2000;100;60;60;P3;1;AP;RESIDENCIAL;300000;300000;ZA;01/06/2026"""


def test_parse_stream_handles_fev_2026_header_variation() -> None:
    rows = list(parse_stream(StringIO(CSV_FEV_2026_HEADERS)))
    assert len(rows) == 1
    assert rows[0].street == "RUA A"
    assert rows[0].neighborhood == "CENTRO"
    assert rows[0].declared_value == 300000.0


CSV_DATA_QUITACAO_TRANSACAO_HEADERS = """Endereco;Bairro;Ano de Construcao Unidade;Area Terreno Total;Area Construida Adquirida;Area Adquirida Unidades Somadas;Padrao Acabamento Unidade;Fracao Ideal Adquirida;Tipo Construtivo Preponderante;Descricao Tipo Ocupacao Unidade;Valor Declarado;Valor Base Calculo;Zona Uso ITBI;Data Quitacao Transacao
RUA A 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG;CENTRO;2000;100;60;60;P3;1;AP;RESIDENCIAL;300000;300000;ZA;01/06/2026"""


def test_parse_stream_handles_data_quitacao_transacao_header() -> None:
    rows = list(parse_stream(StringIO(CSV_DATA_QUITACAO_TRANSACAO_HEADERS)))
    assert len(rows) == 1
    assert rows[0].settlement_date == date(2026, 6, 1)
