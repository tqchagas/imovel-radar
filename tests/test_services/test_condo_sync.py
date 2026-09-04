from datetime import date

import pytest

from app.models.market_comparable import MarketComparable  # noqa: F401  (registra a tabela)
from app.models.portal_building import PortalBuilding
from app.services import condo_sync
from app.services.condo_sync import (
    PortalBlockedError,
    pending_neighborhoods,
    save_buildings,
    select_targets,
    sync_condos,
)
from app.ingestion.quintoandar_condos import parse_condo_page

CIDADE = "belo-horizonte"


def _url(nome, bairro, hash_id):
    return f"https://q/condominio/{nome}-{bairro}-{CIDADE}-{hash_id}"


SAVASSI_A = _url("a", "savassi", "aaaaaaaaaa")
SAVASSI_B = _url("b", "savassi", "bbbbbbbbbb")
BURITIS_C = _url("c", "buritis", "cccccccccc")
CASTELO_D = _url("d", "castelo", "dddddddddd")


def test_select_targets_prefere_o_bairro_mais_carente_e_respeita_o_teto():
    """O orçamento de uma execução vai onde há anúncio sem prédio resolvido:
    baixar as 19.117 páginas seria dezessete gigabytes."""
    entradas = [
        (SAVASSI_A, date(2026, 9, 3)),
        (BURITIS_C, None),
        (SAVASSI_B, None),
        (CASTELO_D, None),
    ]
    alvos = select_targets(
        entradas, ["savassi", "buritis"], conhecidos={}, limit=3, city_slug=CIDADE
    )

    urls = [url for url, _ in alvos]
    assert len(urls) == 3
    assert CASTELO_D not in urls
    assert urls[:2] == sorted([SAVASSI_A, SAVASSI_B])


def test_select_targets_pula_o_que_ja_esta_gravado_e_nao_mudou():
    """O sitemap declara a data; repetir a mesma página é gasto sem resposta."""
    entradas = [(SAVASSI_A, date(2026, 9, 3)), (SAVASSI_B, date(2026, 9, 3))]
    conhecidos = {SAVASSI_A: date(2026, 9, 3), SAVASSI_B: date(2026, 8, 1)}

    alvos = select_targets(
        entradas, ["savassi"], conhecidos=conhecidos, limit=10, city_slug=CIDADE
    )

    assert [url for url, _ in alvos] == [SAVASSI_B]


def test_select_targets_nao_rebaixa_pagina_sem_data_declarada():
    """Sem `lastmod` não há como saber que mudou, e rebaixar repetiria a mesma
    resposta a cada ciclo."""
    alvos = select_targets(
        [(SAVASSI_A, None)],
        ["savassi"],
        conhecidos={SAVASSI_A: None},
        limit=10,
        city_slug=CIDADE,
    )
    assert alvos == []


def test_select_targets_ignora_url_de_outra_cidade():
    outra = f"https://q/condominio/x-moema-sao-paulo-zzz999aaa1"
    alvos = select_targets(
        [(outra, None)], ["moema"], conhecidos={}, limit=10, city_slug=CIDADE
    )
    assert alvos == []


def _anuncio(db, bairro, numero=None, listing_id="1"):
    db.add(
        MarketComparable(
            source="quintoandar",
            listing_id=listing_id,
            cidade_normalizada="belo_horizonte",
            bairro_normalizado=bairro,
            numero_normalizado=numero,
            ativo=True,
        )
    )
    db.flush()


def test_pending_neighborhoods_ordena_pelo_que_falta(db_session):
    """Só o anúncio sem número cria demanda: o que já tem número já alcança o
    tier de endereço."""
    _anuncio(db_session, "savassi", listing_id="1")
    _anuncio(db_session, "savassi", listing_id="2")
    _anuncio(db_session, "buritis", listing_id="3")
    _anuncio(db_session, "castelo", numero="100", listing_id="4")
    db_session.commit()

    assert pending_neighborhoods(db_session, "belo_horizonte") == ["savassi", "buritis"]


CONDO_INFO = {
    "hashId": "1d47sjeomd",
    "slug": "rua-professor-moraes-444-funcionarios-belo-horizonte",
    "lat": -19.937088,
    "lng": -43.931404,
    "address": "Rua Professor Moraes",
    "number": "444",
    "zipCode": "30150-370",
    "neighborhood": "Funcionários",
    "features": {"installations": [{"key": "ELEVADOR", "value": "SIM"}]},
}


def _pagina(hash_id="1d47sjeomd", numero="444"):
    import json

    info = dict(CONDO_INFO, hashId=hash_id, number=numero)
    return (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps({"props": {"pageProps": {"condoInfo": info}}}, ensure_ascii=False)
        + "</script>"
    )


def test_save_buildings_atualiza_em_vez_de_duplicar(db_session):
    """A extração é um retrato, não um diário: a mesma página volta com dado
    novo e substitui o anterior."""
    primeira = parse_condo_page(_pagina(numero="444"), "https://q/x", city="belo_horizonte")
    segunda = parse_condo_page(_pagina(numero="446"), "https://q/x", city="belo_horizonte")

    assert save_buildings(db_session, [primeira]) == 1
    assert save_buildings(db_session, [segunda]) == 1

    gravado = db_session.query(PortalBuilding).one()
    assert gravado.number_key == "446"


def test_sync_condos_baixa_grava_e_respeita_o_teto(db_session, monkeypatch):
    _anuncio(db_session, "funcionarios")
    db_session.commit()

    indice = """<sitemapindex><sitemap><loc>https://q/sitemap-v3-condos-part-0000.xml</loc></sitemap></sitemapindex>"""
    urls = [_url("p", "funcionarios", f"h{i:09d}") for i in range(4)]
    mapa = "<urlset>" + "".join(
        f"<url><loc>{u}</loc><lastmod>2026-09-03</lastmod></url>" for u in urls
    ) + "</urlset>"

    def fetch(url):
        if url.endswith("sitemap-v3.xml"):
            return indice
        if "sitemap-v3-condos" in url:
            return mapa
        return _pagina(hash_id=url[-10:])

    resumo = sync_condos(
        db_session, limit=2, fetch=fetch, sleep=lambda _: None
    )

    assert resumo["alvos"] == 2
    assert resumo["gravados"] == 2
    assert resumo["interrompido"] is None
    assert db_session.query(PortalBuilding).count() == 2


def test_sync_condos_para_na_hora_quando_o_portal_recusa(db_session, monkeypatch):
    """Drenar o teto contra um gateway que acabou de negar é o que transforma
    throttle em bloqueio."""
    _anuncio(db_session, "funcionarios")
    db_session.commit()

    indice = "<sitemapindex><sitemap><loc>https://q/sitemap-v3-condos-part-0000.xml</loc></sitemap></sitemapindex>"
    urls = [_url("p", "funcionarios", f"h{i:09d}") for i in range(5)]
    mapa = "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"
    pedidos = []

    def fetch(url):
        if url.endswith("sitemap-v3.xml"):
            return indice
        if "sitemap-v3-condos" in url:
            return mapa
        pedidos.append(url)
        raise PortalBlockedError("http_429")

    resumo = sync_condos(db_session, limit=5, fetch=fetch, sleep=lambda _: None)

    assert resumo["interrompido"] == "bloqueado:http_429"
    assert len(pedidos) == 1


def test_sync_condos_sem_bairro_pendente_nao_toca_na_rede(db_session):
    """Nada a resolver é resposta, e não motivo para varrer o sitemap."""
    chamadas = []

    def fetch(url):
        chamadas.append(url)
        return ""

    resumo = sync_condos(db_session, fetch=fetch, sleep=lambda _: None)

    assert resumo["alvos"] == 0
    assert chamadas == []


def test_sync_condos_grava_o_que_leu_antes_de_ser_bloqueado(db_session, monkeypatch):
    """Uma execução de 2.500 páginas leva quarenta minutos; um bloqueio no fim
    não pode jogar fora tudo o que já foi lido."""
    monkeypatch.setattr(condo_sync, "SAVE_BATCH", 2)
    _anuncio(db_session, "funcionarios")
    db_session.commit()

    indice = "<sitemapindex><sitemap><loc>https://q/sitemap-v3-condos-part-0000.xml</loc></sitemap></sitemapindex>"
    urls = [_url("p", "funcionarios", f"h{i:09d}") for i in range(5)]
    mapa = "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"
    lidas = []

    def fetch(url):
        if url.endswith("sitemap-v3.xml"):
            return indice
        if "sitemap-v3-condos" in url:
            return mapa
        lidas.append(url)
        if len(lidas) > 4:
            raise PortalBlockedError("http_429")
        return _pagina(hash_id=url[-10:])

    resumo = sync_condos(db_session, limit=5, fetch=fetch, sleep=lambda _: None)

    assert resumo["interrompido"] == "bloqueado:http_429"
    # Quatro páginas lidas, dois lotes de dois gravados antes do bloqueio.
    assert resumo["gravados"] == 4
    assert db_session.query(PortalBuilding).count() == 4
