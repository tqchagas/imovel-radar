import json
from datetime import date

from app.ingestion.quintoandar_condos import (
    condo_entries,
    parse_condo_page,
    sitemap_parts,
    slug_neighborhood,
)

INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex><sitemap><loc>https://www.quintoandar.com.br/sitemap-v3-base-part-0000.xml</loc></sitemap>
<sitemap><loc>https://www.quintoandar.com.br/sitemap-v3-condos-part-0000.xml</loc><lastmod>2026-09-03</lastmod></sitemap>
<sitemap><loc>https://www.quintoandar.com.br/sitemap-v3-condos-part-0001.xml</loc></sitemap>
<sitemap><loc>https://www.quintoandar.com.br/sitemap-v3-condo-city-pages-part-0000.xml</loc></sitemap>
</sitemapindex>"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset><url><loc>https://www.quintoandar.com.br/condominio/rua-professor-moraes-444-funcionarios-belo-horizonte-1d47sjeomd</loc><lastmod>2026-09-03</lastmod></url>
<url><loc>https://www.quintoandar.com.br/condominio/edificio-montreal-savassi-belo-horizonte-abc123xyz9</loc></url>
<url><loc>https://www.quintoandar.com.br/condominio/edificio-paulista-moema-sao-paulo-zzz999aaa1</loc><lastmod>2026-09-03</lastmod></url>
</urlset>"""

CONDO_INFO = {
    "hashId": "1d47sjeomd",
    "name": None,
    "slug": "rua-professor-moraes-444-funcionarios-belo-horizonte",
    "lat": -19.937088012695312,
    "lng": -43.93140411376953,
    "address": "Rua Professor Moraes",
    "number": "444",
    "zipCode": "30150-370",
    "neighborhood": "Funcionários",
    "minArea": 27,
    "maxArea": 58,
    "minBedrooms": 1,
    "maxBedrooms": 2,
    "features": {
        "doorman": "NightAndDayShift",
        "installations": [
            {"key": "PORTARIA_24H", "text": "Portaria 24h", "value": "SIM"},
            {"key": "ELEVADOR", "text": "Elevador", "value": "SIM"},
            {"key": "PISCINA", "text": "Piscina", "value": "NAO"},
        ],
    },
}


def _pagina(condo_info, chave="condoInfo"):
    payload = {"props": {"pageProps": {chave: condo_info}}}
    return (
        '<html><head></head><body><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script></body></html>"
    )


def test_sitemap_parts_fica_so_com_as_particoes_de_condominio():
    """O índice mistura buscas, regiões e páginas de cidade; só uma família de
    arquivos tem uma página por prédio."""
    assert sitemap_parts(INDEX) == [
        "https://www.quintoandar.com.br/sitemap-v3-condos-part-0000.xml",
        "https://www.quintoandar.com.br/sitemap-v3-condos-part-0001.xml",
    ]


def test_condo_entries_filtra_pela_cidade_e_guarda_o_lastmod():
    """O sitemap é nacional: 179.572 páginas, das quais 19.117 são de BH."""
    entradas = condo_entries(SITEMAP, "belo-horizonte")

    assert len(entradas) == 2
    assert entradas[0][1] == date(2026, 9, 3)
    assert entradas[1][1] is None
    assert all("sao-paulo" not in url for url, _ in entradas)


def test_slug_neighborhood_le_o_segmento_antes_da_cidade():
    """Metade dos slugs começa pela rua e a outra metade pelo nome do prédio,
    mas todos terminam em `-{bairro}-{cidade}-{hash}`."""
    assert (
        slug_neighborhood(
            "https://www.quintoandar.com.br/condominio/"
            "rua-professor-moraes-444-funcionarios-belo-horizonte-1d47sjeomd",
            "belo-horizonte",
        )
        == "funcionarios"
    )
    assert (
        slug_neighborhood(
            "https://www.quintoandar.com.br/condominio/"
            "edificio-montreal-savassi-belo-horizonte-abc123xyz9",
            "belo-horizonte",
        )
        == "savassi"
    )


def test_slug_neighborhood_de_outra_cidade_e_nulo():
    assert (
        slug_neighborhood(
            "https://www.quintoandar.com.br/condominio/"
            "edificio-paulista-moema-sao-paulo-zzz999aaa1",
            "belo-horizonte",
        )
        is None
    )


def test_parse_condo_page_extrai_o_numero_da_rua():
    """É o número que o anúncio não publica: 59 de 59 páginas sorteadas o
    trazem, e 83% delas casam com o cadastro da prefeitura por rua+número."""
    row = parse_condo_page(
        _pagina(CONDO_INFO),
        "https://www.quintoandar.com.br/condominio/x-1d47sjeomd",
        city="belo_horizonte",
        lastmod=date(2026, 9, 3),
    )

    assert row is not None
    assert row.source == "quintoandar"
    assert row.external_id == "1d47sjeomd"
    assert row.street == "Rua Professor Moraes"
    assert row.street_number == "444"
    assert row.street_key == "rua_professor_moraes"
    assert row.number_key == "444"
    assert row.postal_code == "30150-370"
    assert row.neighborhood == "Funcionários"
    assert row.lat == -19.937088
    assert row.lon == -43.931404
    assert row.min_area == 27
    assert row.max_area == 58
    assert row.min_bedrooms == 1
    assert row.max_bedrooms == 2
    assert row.doorman == "NightAndDayShift"
    assert row.source_lastmod == date(2026, 9, 3)


def test_parse_condo_page_guarda_so_a_instalacao_presente():
    """"NAO" é resposta e não ausência; guardar as duas encheria a coluna de
    ruído e faria a contagem de comodidades dizer o contrário do que diz."""
    row = parse_condo_page(_pagina(CONDO_INFO), "https://x/y", city="belo_horizonte")

    assert row is not None
    assert row.installations == ["ELEVADOR", "PORTARIA_24H"]


def test_parse_condo_page_acha_o_condo_info_fora_do_lugar():
    """O portal já moveu a chave entre versões do bundle; procurar custa menos
    do que reagir a isso depois."""
    payload = {"props": {"pageProps": {"initialState": {"condoInfo": CONDO_INFO}}}}
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>"
    )
    row = parse_condo_page(html, "https://x/y", city="belo_horizonte")

    assert row is not None and row.street_number == "444"


def test_parse_condo_page_sem_numero_e_descartada():
    """Sem número a página não responde à pergunta que a fez ser baixada."""
    sem_numero = dict(CONDO_INFO, number=None)
    assert (
        parse_condo_page(_pagina(sem_numero), "https://x/y", city="belo_horizonte") is None
    )


def test_parse_condo_page_sem_rua_e_descartada():
    sem_rua = dict(CONDO_INFO, address="")
    assert parse_condo_page(_pagina(sem_rua), "https://x/y", city="belo_horizonte") is None


def test_parse_condo_page_sem_next_data_e_descartada():
    assert parse_condo_page("<html></html>", "https://x/y", city="belo_horizonte") is None


def test_parse_condo_page_com_json_quebrado_e_descartada():
    html = '<script id="__NEXT_DATA__" type="application/json">{"props":</script>'
    assert parse_condo_page(html, "https://x/y", city="belo_horizonte") is None


def test_parse_condo_page_sem_condo_info_e_descartada():
    assert (
        parse_condo_page(
            _pagina(CONDO_INFO, chave="houseInfo"), "https://x/y", city="belo_horizonte"
        )
        is None
    )
