"""O fator que traz um valor antigo para o mês de referência.

Os números conferidos aqui saem da série 433 do SGS baixada em 2026-09-09 e da
convenção da Calculadora do Cidadão: a variação do mês inicial não entra.
"""

from datetime import date

import pytest

from app.ingestion.bcb_sgs import IndexPoint
from app.domain.monetary_correction import Deflator, competencia_de


@pytest.fixture()
def deflator() -> Deflator:
    # Três meses de 10%: de jan a abr acumula 1,331; de fev a abr, 1,21.
    return Deflator.from_points(
        [
            IndexPoint(date(2024, 1, 1), 0.0),
            IndexPoint(date(2024, 2, 1), 10.0),
            IndexPoint(date(2024, 3, 1), 10.0),
            IndexPoint(date(2024, 4, 1), 10.0),
        ]
    )


def test_a_referencia_e_o_ultimo_mes_da_serie(deflator):
    assert deflator.referencia == date(2024, 4, 1)


def test_o_mes_de_referencia_vale_um(deflator):
    assert deflator.fator(date(2024, 4, 1)) == pytest.approx(1.0)


def test_a_variacao_do_proprio_mes_da_quitacao_nao_entra(deflator):
    # Quitou em fevereiro: corrige por março e abril, não por fevereiro.
    assert deflator.fator(date(2024, 2, 1)) == pytest.approx(1.21)


def test_acumula_do_primeiro_mes(deflator):
    assert deflator.fator(date(2024, 1, 1)) == pytest.approx(1.331)


def test_mes_anterior_ao_inicio_da_serie_nao_tem_fator(deflator):
    assert deflator.fator(date(2007, 12, 1)) is None


def test_mes_ainda_nao_publicado_nao_tem_fator(deflator):
    # Nunca 1,0: sem medida, não inventa.
    assert deflator.fator(date(2024, 5, 1)) is None


def test_corrigir_aplica_o_fator(deflator):
    assert deflator.corrigir(100_000, date(2024, 2, 1)) == pytest.approx(121_000)


def test_corrigir_sem_fator_devolve_none(deflator):
    assert deflator.corrigir(100_000, date(2024, 5, 1)) is None


def test_corrigir_valor_nulo_devolve_none(deflator):
    assert deflator.corrigir(None, date(2024, 2, 1)) is None


def test_a_data_da_quitacao_vira_o_primeiro_dia_do_mes():
    assert competencia_de(date(2024, 2, 29)) == date(2024, 2, 1)


def test_corrigir_aceita_a_data_exata_da_quitacao(deflator):
    assert deflator.corrigir(100_000, date(2024, 2, 17)) == pytest.approx(121_000)


def test_serie_vazia_nao_vira_deflator():
    with pytest.raises(ValueError):
        Deflator.from_points([])


def test_fator_conhecido_do_ipca():
    # jun/2019 -> jul/2026 mede 1,469 na série real. O teste usa a variação
    # equivalente em vez da rede: o que se prova aqui é a aritmética.
    pontos = [IndexPoint(date(2019, 6, 1), 0.0)]
    acumulado = 1.469 ** (1 / 85)  # 85 meses de jul/2019 a jul/2026
    mes = date(2019, 7, 1)
    for _ in range(85):
        pontos.append(IndexPoint(mes, (acumulado - 1) * 100))
        ano, m = divmod(mes.year * 12 + mes.month, 12)
        mes = date(ano, m + 1, 1) if m + 1 <= 12 else date(ano + 1, 1, 1)
    deflator = Deflator.from_points(pontos)
    assert deflator.fator(date(2019, 6, 1)) == pytest.approx(1.469, rel=1e-3)
