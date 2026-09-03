from datetime import date, timedelta

from app.domain.market_stats import Sale
from app.domain.outcomes import (
    AREA_RATIO_MAX,
    AREA_RATIO_MIN,
    LOOKAHEAD_DAYS,
    LOOKBACK_DAYS,
    match_outcome,
    plausible_area,
    within_window,
)

SAIDA = date(2026, 6, 1)


def _venda(settlement: date, area: float | None = 128.0, valor: float = 900_000.0) -> Sale:
    return Sale(
        neighborhood="SAVASSI",
        street="Rua Sao Joao",
        street_number="10",
        settlement_date=settlement,
        declared_value=valor,
        built_area_acquired=area,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        transaction_id=1,
    )


def test_a_janela_abre_para_os_dois_lados_da_saida():
    assert within_window(SAIDA - timedelta(days=LOOKBACK_DAYS), SAIDA)
    assert within_window(SAIDA + timedelta(days=LOOKAHEAD_DAYS), SAIDA)
    assert not within_window(SAIDA - timedelta(days=LOOKBACK_DAYS + 1), SAIDA)
    assert not within_window(SAIDA + timedelta(days=LOOKAHEAD_DAYS + 1), SAIDA)


def test_a_janela_olha_mais_para_frente_do_que_para_tras():
    # O ITBI chega atrasado, então o par quase sempre está no futuro da saída.
    assert LOOKAHEAD_DAYS > LOOKBACK_DAYS


def test_area_plausivel_aceita_a_variacao_medida_entre_predios():
    assert plausible_area(_venda(SAIDA, area=80 * AREA_RATIO_MIN), 80.0)
    assert plausible_area(_venda(SAIDA, area=80 * AREA_RATIO_MAX), 80.0)
    assert not plausible_area(_venda(SAIDA, area=80 * (AREA_RATIO_MIN - 0.1)), 80.0)
    assert not plausible_area(_venda(SAIDA, area=80 * (AREA_RATIO_MAX + 0.1)), 80.0)


def test_area_desconhecida_de_qualquer_lado_nao_descarta():
    # Faltando área, o endereço e a data ainda sustentam o par.
    assert plausible_area(_venda(SAIDA, area=None), 80.0)
    assert plausible_area(_venda(SAIDA, area=128.0), None)
    assert plausible_area(_venda(SAIDA, area=128.0), 0.0)


def test_vence_a_quitacao_mais_proxima_da_saida():
    vendas = [
        _venda(SAIDA + timedelta(days=200), valor=700_000.0),
        _venda(SAIDA + timedelta(days=20), valor=900_000.0),
        _venda(SAIDA - timedelta(days=90), valor=800_000.0),
    ]
    achado = match_outcome(vendas, delisted_on=SAIDA, area_anunciada=80.0)
    assert achado is not None
    assert achado.sale.declared_value == 900_000.0
    assert achado.candidatos == 3


def test_o_numero_de_candidatas_e_registrado():
    achado = match_outcome(
        [_venda(SAIDA + timedelta(days=10))], delisted_on=SAIDA, area_anunciada=80.0
    )
    assert achado is not None and achado.candidatos == 1


def test_sem_quitacao_na_janela_nao_ha_desfecho():
    fora = [_venda(SAIDA + timedelta(days=LOOKAHEAD_DAYS + 30))]
    assert match_outcome(fora, delisted_on=SAIDA, area_anunciada=80.0) is None
    assert match_outcome([], delisted_on=SAIDA, area_anunciada=80.0) is None


def test_area_incompativel_exclui_a_candidata():
    # Uma vaga de garagem vendida no mesmo prédio, na mesma semana.
    vaga = _venda(SAIDA + timedelta(days=5), area=12.0, valor=40_000.0)
    assert match_outcome([vaga], delisted_on=SAIDA, area_anunciada=80.0) is None


def test_o_par_nao_usa_preco():
    # Duas quitações igualmente próximas em data, preços muito diferentes: a
    # escolha não pode preferir a que se parece com o preço anunciado, porque é
    # justamente essa diferença que o desfecho existe para medir.
    barata = _venda(SAIDA + timedelta(days=10), valor=100_000.0)
    cara = _venda(SAIDA + timedelta(days=11), valor=900_000.0)
    achado = match_outcome([cara, barata], delisted_on=SAIDA, area_anunciada=80.0)
    assert achado is not None and achado.sale.declared_value == 100_000.0
