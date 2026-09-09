from datetime import date

import pytest

from app.domain.market_stats import Sale
from app.domain.monetary_correction import Deflator
from app.domain.street_stats import street_detail
from app.ingestion.bcb_sgs import IndexPoint


def _sale(
    street: str,
    value: float,
    area: float | None,
    when: date,
    number: str,
) -> Sale:
    return Sale(
        neighborhood="SAVASSI",
        street=street,
        settlement_date=when,
        declared_value=value,
        built_area_acquired=area,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
        street_number=number,
    )


def test_street_detail_summarizes_ticket_area_and_distinct_addresses() -> None:
    sales = [
        _sale("RUA A", 100_000, 50, date(2025, 1, 1), "10"),
        _sale("RUA A", 200_000, 100, date(2025, 2, 1), "20"),
        _sale("RUA A", 300_000, None, date(2025, 3, 1), "10"),
        _sale("RUA A", 50_000, 50, date(2023, 1, 1), "30"),
        _sale("RUA B", 999_000, 100, date(2025, 3, 1), "1"),
    ]

    result = street_detail(sales, street="RUA A", reference=date(2025, 3, 1), months=12)

    assert result.transaction_count == 3
    assert result.property_count == 2
    assert result.median_ticket == 200_000
    assert result.median_price_per_m2 == 2_000
    assert result.median_area == 75
    assert result.top_addresses[0].street_number == "10"


REFERENCIA = date(2026, 2, 28)


def _venda(dia: date, valor: float = 500_000) -> Sale:
    return Sale(
        neighborhood="CENTRO",
        street="RUA A",
        settlement_date=dia,
        declared_value=valor,
        built_area_acquired=100,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
    )


def _deflator_jan_fev() -> Deflator:
    """Fev é a referência; jan acumula 10% até lá."""
    return Deflator.from_points(
        [IndexPoint(date(2026, 1, 1), 0.0), IndexPoint(date(2026, 2, 1), 10.0)]
    )


def test_a_mediana_corrigida_corrige_venda_a_venda():
    # Duas vendas de R$ 5.000/m², uma em jan e outra em fev. A mediana nominal
    # é 5.000; a corrigida é a mediana de (5.500, 5.000) = 5.250. Corrigir a
    # mediana pronta pelo fator do mês do meio daria outro número, e o errado.
    detalhe = street_detail(
        [_venda(date(2026, 1, 15)), _venda(date(2026, 2, 15))],
        "RUA A",
        reference=REFERENCIA,
        months=12,
        deflator=_deflator_jan_fev(),
    )
    assert detalhe.median_price_per_m2 == pytest.approx(5_000)
    assert detalhe.median_price_per_m2_corrected == pytest.approx(5_250)


def test_sem_deflator_a_saida_e_a_de_hoje():
    # A garantia de que nenhum número já validado se move.
    detalhe = street_detail(
        [_venda(date(2026, 1, 15)), _venda(date(2026, 2, 15))],
        "RUA A",
        reference=REFERENCIA,
        months=12,
    )
    assert detalhe.median_price_per_m2_corrected is None
    assert detalhe.median_price_per_m2 == pytest.approx(5_000)


def test_venda_sem_fator_fica_de_fora_da_mediana_corrigida():
    # Dez/2025 está fora da série. Deixar ela entrar pelo valor nominal
    # misturaria duas réguas na mesma mediana — o resultado não seria nem uma
    # coisa nem outra. A nominal continua contando as duas.
    detalhe = street_detail(
        [_venda(date(2025, 12, 15)), _venda(date(2026, 1, 15))],
        "RUA A",
        reference=REFERENCIA,
        months=12,
        deflator=_deflator_jan_fev(),
    )
    assert detalhe.transaction_count == 2
    assert detalhe.median_price_per_m2 == pytest.approx(5_000)
    assert detalhe.median_price_per_m2_corrected == pytest.approx(5_500)
