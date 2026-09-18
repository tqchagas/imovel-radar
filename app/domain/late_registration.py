"""Quitação de ITBI que carrega o preço de um contrato antigo.

O ITBI de Belo Horizonte publica a data de quitação, não a data do negócio. Quem
compra na planta costuma quitar o imposto só na escritura, anos depois, e
declara o valor do contrato de lançamento. A quitação cai numa data recente com
um preço de anos atrás: puxa para baixo o R$/m² da rua e do bairro e inventa
valorizações ("o 302 dobrou de preço") quando a unidade é revendida.

Na base, a primeira quitação de uma unidade que aparece anos depois do
lançamento do prédio sai, na mediana, pelo R$/m² do lançamento (1,06× depois de
três anos), enquanto as revendas do mesmo prédio na mesma idade já estão em
1,26×. É essa assinatura que se marca aqui:

1. é a primeira quitação da unidade (rua, número e complemento);
2. o prédio teve o lançamento dentro da cobertura da base — a primeira quitação
   dele caiu perto do ano de construção, e o ano de construção é posterior ao
   início da base;
3. a quitação vem pelo menos `MIN_YEARS_AFTER_LAUNCH` anos depois da primeira
   quitação do prédio;
4. o R$/m² dela não passa de `MAX_LAUNCH_PRICE_RATIO` vezes a mediana do R$/m²
   das primeiras quitações do primeiro ano do prédio.

Declarado abaixo da base de cálculo não entra: ~40% da base inteira está assim,
em qualquer época, e o sinal não separa contrato antigo de subdeclaração.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.complement import normalize_complement, normalize_street_key

MIN_YEARS_AFTER_LAUNCH = 2
MAX_LAUNCH_PRICE_RATIO = 1.10
# Janela do "lançamento": primeiras quitações no primeiro ano do prédio.
LAUNCH_WINDOW = timedelta(days=365)
MIN_LAUNCH_SALES = 3
# A primeira quitação do prédio precisa cair a até tantos anos do ano de
# construção para ser o lançamento, e não só a primeira revenda que a base viu.
MAX_LAUNCH_TO_CONSTRUCTION_YEARS = 2


@dataclass(frozen=True)
class Settlement:
    id: int
    street: str
    street_number: str | None
    complement: str | None
    settlement_date: date
    declared_value: float
    built_area_acquired: float | None
    construction_year: int | None


def _price_per_m2(s: Settlement) -> float | None:
    if s.built_area_acquired is None or s.built_area_acquired <= 0 or s.declared_value <= 0:
        return None
    return s.declared_value / s.built_area_acquired


def _years_between(start: date, end: date) -> float:
    return (end - start).days / 365.25


def flag_late_registrations(
    settlements: Iterable[Settlement], *, coverage_start: date
) -> set[int]:
    """Ids das quitações que parecem contrato de lançamento registrado tarde.

    `coverage_start` é a quitação mais antiga da base da cidade: prédio
    construído antes dela teve o lançamento fora da base, e a "primeira
    quitação" dele é só a primeira revenda que a base viu.
    """
    buildings: dict[tuple[str, str], dict[str, list[Settlement]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for s in settlements:
        unit = normalize_complement(s.complement)
        number = (s.street_number or "").strip().upper()
        if not unit or not number:
            continue
        buildings[(normalize_street_key(s.street), number)][unit].append(s)

    flagged: set[int] = set()
    for units in buildings.values():
        first_sales = [
            min(history, key=lambda s: (s.settlement_date, s.id)) for history in units.values()
        ]
        flagged.update(_late_in_building(first_sales, coverage_start))
    return flagged


def _late_in_building(first_sales: list[Settlement], coverage_start: date) -> set[int]:
    years = [s.construction_year for s in first_sales if s.construction_year]
    if not years:
        return set()
    construction_year = int(statistics.median(years))
    if construction_year <= coverage_start.year:
        return set()

    launch = min(s.settlement_date for s in first_sales)
    if abs(launch.year - construction_year) > MAX_LAUNCH_TO_CONSTRUCTION_YEARS:
        return set()

    launch_prices = [
        p
        for s in first_sales
        if s.settlement_date < launch + LAUNCH_WINDOW and (p := _price_per_m2(s)) is not None
    ]
    if len(launch_prices) < MIN_LAUNCH_SALES:
        return set()
    ceiling = statistics.median(launch_prices) * MAX_LAUNCH_PRICE_RATIO

    return {
        s.id
        for s in first_sales
        if _years_between(launch, s.settlement_date) >= MIN_YEARS_AFTER_LAUNCH
        and (p := _price_per_m2(s)) is not None
        and p <= ceiling
    }
