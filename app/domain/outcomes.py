"""Casa um anúncio que saiu do ar com a quitação de ITBI que o explica.

O anúncio some do portal quando o negócio fecha; o ITBI aparece quando o
imposto é pago. As duas datas não coincidem e nem sempre estão na mesma ordem —
o imposto costuma ser recolhido antes da escritura, e o anúncio às vezes sai do
ar semanas depois do sinal. Por isso a janela abre para os dois lados.

O par é feito por endereço e por área, nunca por preço: casar por preço
assumiria justamente a resposta que o desfecho existe para medir.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from app.domain.market_stats import Sale

# Quanto antes da saída do anúncio a quitação ainda a explica. O imposto é
# recolhido antes da escritura, e um anúncio pode continuar no ar por inércia.
LOOKBACK_DAYS = 120
# Quanto depois. O ITBI de Belo Horizonte chega com dois meses de atraso, e
# entre o negócio e a quitação passam-se semanas ou meses.
LOOKAHEAD_DAYS = 240
# Tolerância de área entre o que o anúncio publicava e o que o cartório lançou.
# Mais larga do que a da escada de referência de propósito: aqui não se procura
# um comparável e sim a *mesma* unidade, e a razão entre as duas áreas varia de
# 0,80 a 2,21 entre prédios.
AREA_RATIO_MIN = 0.6
AREA_RATIO_MAX = 2.6

MATCH_BY_ADDRESS = "endereco"
MATCH_BY_COORDINATE = "coordenada"


@dataclass(frozen=True)
class OutcomeMatch:
    """A quitação escolhida para um anúncio, e quantas disputaram."""

    sale: Sale
    candidatos: int


def within_window(settlement: date, delisted: date) -> bool:
    return (
        delisted - timedelta(days=LOOKBACK_DAYS)
        <= settlement
        <= delisted + timedelta(days=LOOKAHEAD_DAYS)
    )


def plausible_area(sale: Sale, area_anunciada: float | None) -> bool:
    """A área do cartório pode descrever a unidade que o anúncio publicava?"""
    if area_anunciada is None or area_anunciada <= 0:
        return True
    construida = sale.built_area_acquired
    if construida is None or float(construida) <= 0:
        return True
    razao = float(construida) / area_anunciada
    return AREA_RATIO_MIN <= razao <= AREA_RATIO_MAX


def match_outcome(
    sales_no_endereco: Sequence[Sale],
    *,
    delisted_on: date,
    area_anunciada: float | None,
) -> OutcomeMatch | None:
    """A quitação mais próxima da saída do anúncio, entre as plausíveis.

    Havendo mais de uma candidata, vence a que fechou mais perto da data em que
    o anúncio saiu do ar — e o número de candidatas é registrado, porque um par
    disputado não vale o mesmo que um par único.
    """
    candidatas = [
        venda
        for venda in sales_no_endereco
        if within_window(venda.settlement_date, delisted_on)
        and plausible_area(venda, area_anunciada)
    ]
    if not candidatas:
        return None
    escolhida = min(candidatas, key=lambda v: abs((v.settlement_date - delisted_on).days))
    return OutcomeMatch(sale=escolhida, candidatos=len(candidatas))
