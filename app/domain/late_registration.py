"""Quitação de ITBI que carrega o preço de um contrato antigo.

O ITBI de Belo Horizonte publica a data de quitação, não a data do negócio. Quem
compra na planta costuma quitar o imposto só na escritura, anos depois, e
declara o valor do contrato de lançamento. A quitação cai numa data recente com
um preço de anos atrás: puxa para baixo o R$/m² da rua e do bairro e inventa
valorizações ("o 302 dobrou de preço") quando a unidade é revendida.

Na base, a primeira quitação de uma unidade que aparece anos depois do
lançamento do prédio sai, na mediana, pelo R$/m² do lançamento (1,06× depois de
três anos), enquanto as revendas do mesmo prédio na mesma idade já estão em
1,26×. É essa assinatura que se marca aqui. A quitação candidata:

1. é a primeira quitação da unidade (rua, número e complemento);
2. é de um prédio lançado dentro da cobertura da base — a primeira quitação
   dele caiu perto do ano de construção, e o ano de construção é posterior ao
   início da base. Prédio mais antigo não tem "primeira venda" na base, só a
   primeira revenda que ela viu;
3. vem pelo menos `min_years_after_launch` anos depois da primeira quitação do
   prédio;
4. declara abaixo da base de cálculo da prefeitura.

E o preço dela é medido contra duas referências do mesmo prédio e tipo:

- o lançamento: a mediana do R$/m² das primeiras quitações do primeiro ano do
  prédio. A candidata passa se não sair acima de `max_launch_price_ratio` vezes
  isso;
- as revendas do prédio a até `resale_window` dela. A candidata passa se sair
  abaixo de `max_resale_price_ratio` vezes a mediana delas.

Passar nas duas dá confiança alta; passar na única que existe, média; falhar em
qualquer uma que exista, nenhuma marca. A revenda é o melhor juiz — é o preço
de mercado do prédio naquele ano —, mas nem todo prédio tem revenda por perto,
e nem todo prédio teve vendas bastantes no lançamento.

O prédio é comparado por tipo construtivo — apartamento com apartamento, sala
com sala —, porque o R$/m² de uma loja ou de uma sala não diz nada sobre o de um
apartamento. Vaga de garagem fica fora: a área dela é pequena e varia muito,
então o R$/m² da vaga não serve para medir preço.

A condição 4 sozinha não marcaria nada: ~40% da base inteira declara abaixo da
base de cálculo, em qualquer época. Mas, entre as candidatas que passam no
lançamento, as que declaram o mesmo valor da base saem a 0,98× o R$/m² das
revendas do mesmo prédio no mesmo ano: preço de mercado, estoque da construtora
vendido tarde. As que declaram abaixo saem a 0,78×.

Os limites de `LateRule` foram calibrados com `scripts/validar_tardios.py`, que
mede o erro da referência de preço com e sem as quitações marcadas. Em Belo
Horizonte (set/2026), nos prédios com marca, tirá-las leva o erro mediano de
10,5% para 10,0% e o viés de -2,6% para -1,2%. A comparação com as revendas
marca 1.900 quitações a menos que o lançamento sozinho, sem mudar o erro: eram
preço de mercado. Tirar só as de confiança alta erra mais (10,1%).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.domain.complement import normalize_complement, normalize_street_key

Confidence = Literal["alta", "media"]

# Vagas de garagem: coberta, residencial e garagem-prédio.
PARKING_TYPES = frozenset({"VC", "VR", "GP"})


@dataclass(frozen=True)
class LateRule:
    min_years_after_launch: float = 2.0
    max_launch_price_ratio: float = 1.10
    # Declarado a partir disto da base de cálculo conta como "igual à base".
    base_agreement_ratio: float = 0.99
    # Janela do "lançamento": primeiras quitações no primeiro ano do prédio.
    launch_window: timedelta = timedelta(days=365)
    min_launch_sales: int = 3
    # A primeira quitação do prédio precisa cair a até tantos anos do ano de
    # construção para ser o lançamento, e não só a primeira revenda que a base viu.
    max_launch_to_construction_years: int = 2
    resale_window: timedelta = timedelta(days=365)
    min_resales: int = 2
    # None desliga a comparação com as revendas.
    max_resale_price_ratio: float | None = 0.90


DEFAULT_RULE = LateRule()


@dataclass(frozen=True)
class Settlement:
    id: int
    street: str
    street_number: str | None
    complement: str | None
    settlement_date: date
    declared_value: float
    calc_base_value: float
    built_area_acquired: float | None
    construction_year: int | None
    construction_type: str | None


def _price_per_m2(s: Settlement) -> float | None:
    if s.built_area_acquired is None or s.built_area_acquired <= 0 or s.declared_value <= 0:
        return None
    return s.declared_value / s.built_area_acquired


def _years_between(start: date, end: date) -> float:
    return (end - start).days / 365.25


def flag_late_registrations(
    settlements: Iterable[Settlement],
    *,
    coverage_start: date,
    rule: LateRule = DEFAULT_RULE,
) -> dict[int, Confidence]:
    """Quitações que parecem contrato de lançamento registrado tarde, com a confiança.

    `coverage_start` é a quitação mais antiga da base da cidade: prédio
    construído antes dela teve o lançamento fora da base.
    """
    buildings: dict[tuple[str, str, str], dict[str, list[Settlement]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for s in settlements:
        unit = normalize_complement(s.complement)
        number = (s.street_number or "").strip().upper()
        kind = (s.construction_type or "").strip().upper()
        if not unit or not number or kind in PARKING_TYPES:
            continue
        buildings[(normalize_street_key(s.street), number, kind)][unit].append(s)

    flagged: dict[int, Confidence] = {}
    for units in buildings.values():
        flagged.update(_late_in_building(units, coverage_start, rule))
    return flagged


def _late_in_building(
    units: dict[str, list[Settlement]], coverage_start: date, rule: LateRule
) -> dict[int, Confidence]:
    histories = [sorted(h, key=lambda s: (s.settlement_date, s.id)) for h in units.values()]
    first_sales = [h[0] for h in histories]
    resales = [
        (s.settlement_date, p)
        for h in histories
        for s in h[1:]
        if (p := _price_per_m2(s)) is not None
    ]

    years = [s.construction_year for s in first_sales if s.construction_year]
    if not years:
        return {}
    construction_year = int(statistics.median(years))
    if construction_year <= coverage_start.year:
        return {}
    launch = min(s.settlement_date for s in first_sales)
    if abs(launch.year - construction_year) > rule.max_launch_to_construction_years:
        return {}

    launch_prices = [
        p
        for s in first_sales
        if s.settlement_date < launch + rule.launch_window
        and (p := _price_per_m2(s)) is not None
    ]
    launch_ceiling = (
        statistics.median(launch_prices) * rule.max_launch_price_ratio
        if len(launch_prices) >= rule.min_launch_sales
        else None
    )

    flagged: dict[int, Confidence] = {}
    for s in first_sales:
        price = _price_per_m2(s)
        if (
            price is None
            or _years_between(launch, s.settlement_date) < rule.min_years_after_launch
            or s.declared_value >= s.calc_base_value * rule.base_agreement_ratio
        ):
            continue
        checks: list[bool] = []
        if launch_ceiling is not None:
            checks.append(price <= launch_ceiling)
        if rule.max_resale_price_ratio is not None:
            nearby = [
                p for d, p in resales if abs((d - s.settlement_date).days) <= rule.resale_window.days
            ]
            if len(nearby) >= rule.min_resales:
                checks.append(price < statistics.median(nearby) * rule.max_resale_price_ratio)
        if checks and all(checks):
            flagged[s.id] = "alta" if len(checks) == 2 else "media"
    return flagged
