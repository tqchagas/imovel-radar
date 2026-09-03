import io

from app.ingestion.pbh_registry import (
    RegistryRow,
    aggregate,
    parse_file,
    resource_urls,
)

CABECALHO = (
    "TIPO_CONSTRUTIVO;TIPO_OCUPACAO;PADRAO_ACABAMENTO;AREA_CONSTRUCAO;"
    "TIPO_LOGRADOURO;NOME_LOGRADOURO;NUMERO_IMOVEL;CEP;GEOMETRIA"
)


def _linha(
    tipo="APARTAMENTO",
    ocupacao="RESIDENCIAL",
    padrao="P3",
    area="86.95",
    tipo_log="AVE",
    nome="AUGUSTO DE LIMA",
    numero="134",
    cep="30140074",
    geometria="POLYGON ((610785.44 7796257,610779.94 7796258.5,610766.25 7796262,610785.44 7796257))",
):
    return f"{tipo};{ocupacao};{padrao};{area};{tipo_log};{nome};{numero};{cep};{geometria}"


def _csv(*linhas):
    return io.StringIO("\n".join([CABECALHO, *linhas]))


def _uma(*linhas) -> RegistryRow:
    resultado = list(parse_file(_csv(*linhas)))
    assert len(resultado) == 1
    return resultado[0]


def test_a_chave_de_rua_expande_a_abreviacao_do_cadastro():
    row = _uma(_linha())
    assert row.street_key == "avenida_augusto_de_lima"
    assert row.number_key == "134"
    assert row.street == "AVE AUGUSTO DE LIMA"


def test_o_tipo_construtivo_vira_a_sigla_do_itbi():
    assert _uma(_linha(tipo="APARTAMENTO")).construction_type == "AP"
    assert _uma(_linha(tipo="CASA")).construction_type == "CA"


def test_tipo_que_a_escada_nao_compara_e_descartado():
    assert list(parse_file(_csv(_linha(tipo="LOJA"), _linha(tipo="VAGA DE GARAGEM RESIDENCIAL")))) == []


def test_a_geometria_utm_vira_latitude_e_longitude_de_bh():
    row = _uma(_linha())
    assert row.lat is not None and row.lon is not None
    assert -20.10 < row.lat < -19.70
    assert -44.10 < row.lon < -43.80


def test_economias_do_mesmo_endereco_viram_uma_linha_so():
    row = _uma(_linha(area="80"), _linha(area="90"), _linha(area="100"))
    assert row.units_count == 3
    assert float(row.median_unit_area) == 90.0


def test_a_coordenada_do_endereco_e_a_mediana_e_nao_a_media():
    # Um lote com geometria disparatada não pode arrastar o endereço.
    torto = "POLYGON ((900000 7000000,900001 7000000,900001 7000001,900000 7000000))"
    row = _uma(_linha(), _linha(), _linha(geometria=torto))
    normal = _uma(_linha())
    assert row.lat == normal.lat
    assert row.lon == normal.lon


def test_o_padrao_de_acabamento_e_o_predominante():
    row = _uma(_linha(padrao="P4"), _linha(padrao="P3"), _linha(padrao="P3"))
    assert row.finish_standard == "P3"


def test_enderecos_diferentes_no_mesmo_arquivo_nao_se_misturam():
    linhas = [_linha(numero="134"), _linha(numero="500"), _linha(nome="DOS AIMORES", tipo_log="RUA")]
    resultado = {(r.street_key, r.number_key) for r in parse_file(_csv(*linhas))}
    assert resultado == {
        ("avenida_augusto_de_lima", "134"),
        ("avenida_augusto_de_lima", "500"),
        ("rua_dos_aimores", "134"),
    }


def test_apartamento_e_casa_no_mesmo_endereco_ficam_separados():
    resultado = list(parse_file(_csv(_linha(tipo="APARTAMENTO"), _linha(tipo="CASA"))))
    assert sorted(r.construction_type for r in resultado) == ["AP", "CA"]


def test_linha_sem_numero_ou_sem_logradouro_e_ignorada():
    assert list(parse_file(_csv(_linha(numero=""), _linha(nome="", tipo_log="")))) == []


def test_linha_sem_geometria_ainda_vale_pelo_endereco():
    row = _uma(_linha(geometria=""))
    assert row.lat is None and row.street_key == "avenida_augusto_de_lima"


def test_a_data_da_extracao_vem_do_nome_do_recurso():
    row = next(iter(aggregate([], source_stamp="20260701")), None)
    assert row is None  # sem linhas, sem endereços
    row = list(parse_file(_csv(_linha()), source_stamp="20260701"))[0]
    assert row.source_date is not None
    assert (row.source_date.year, row.source_date.month, row.source_date.day) == (2026, 7, 1)


def test_data_de_extracao_invalida_nao_quebra():
    assert list(parse_file(_csv(_linha()), source_stamp="julho"))[0].source_date is None
    assert list(parse_file(_csv(_linha())))[0].source_date is None


def test_resource_urls_escolhe_a_extracao_mais_recente_de_cada_regional():
    payload = {
        "result": {
            "results": [
                {
                    "name": "cadastro-imobiliario-regional-norte",
                    "resources": [
                        {
                            "format": "CSV",
                            "name": "20260601_regional_norte_cadastro_imobiliario",
                            "url": "https://exemplo/junho.csv",
                        },
                        {
                            "format": "CSV",
                            "name": "20260701_regional_norte_cadastro_imobiliario",
                            "url": "https://exemplo/julho.csv",
                        },
                        {"format": "PDF", "name": "dicionario", "url": "https://exemplo/doc.pdf"},
                    ],
                },
                {
                    "name": "outro-conjunto-qualquer",
                    "resources": [
                        {
                            "format": "CSV",
                            "name": "20260701_regional_norte_cadastro_imobiliario",
                            "url": "https://exemplo/nao-e-cadastro.csv",
                        }
                    ],
                },
            ]
        }
    }
    assert resource_urls(payload) == {"norte": ("20260701", "https://exemplo/julho.csv")}


def test_resource_urls_de_payload_vazio_e_vazio():
    assert resource_urls({}) == {}
    assert resource_urls({"result": {"results": []}}) == {}
