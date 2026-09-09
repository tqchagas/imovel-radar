"""Trazer um valor antigo para o mês de referência.

A série guarda variação mensal; o fator entre dois meses é o produto das
variações no intervalo. A convenção é a da Calculadora do Cidadão do Banco
Central: corrigir de M até R aplica a variação dos meses em (M, R] — a variação
do próprio mês da quitação não entra. Fixar isso em um lugar só importa: sem
convenção declarada, dois pontos do código dariam números diferentes para o
mesmo ITBI e ninguém saberia qual está certo.

Mês sem índice devolve None, nunca 1,0. É a mesma regra do fator de calibração
das oportunidades: sem medida, não inventa.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date


def competencia_de(dia: date) -> date:
    """Qualquer data vira o primeiro dia do seu mês."""
    return date(dia.year, dia.month, 1)


@dataclass(frozen=True)
class Deflator:
    referencia: date
    # Mês -> índice acumulado incluindo a variação do próprio mês.
    _acumulado: dict[date, float]

    @classmethod
    def from_points(cls, points: Iterable) -> Deflator:
        # Aceita qualquer Iterable com .competencia e .variacao_pct, sem restringir
        # a IndexPoint, porque o próximo task alimenta MonetaryIndex do banco em vez
        # de IndexPoint. Ambos têm os dois campos; variacao_pct chega como Decimal
        # do banco e float do coletor, então envolve em float(...).
        ordenados = sorted(points, key=lambda p: p.competencia)
        if not ordenados:
            raise ValueError("Série vazia: não há como corrigir valor nenhum.")
        acumulado: dict[date, float] = {}
        corrente = 1.0
        for ponto in ordenados:
            corrente *= 1 + float(ponto.variacao_pct) / 100
            acumulado[ponto.competencia] = corrente
        return cls(referencia=ordenados[-1].competencia, _acumulado=acumulado)

    def fator(self, competencia: date) -> float | None:
        mes = competencia_de(competencia)
        base = self._acumulado.get(mes)
        if base is None:
            return None
        return self._acumulado[self.referencia] / base

    def corrigir(self, valor: float | None, competencia: date) -> float | None:
        if valor is None:
            return None
        fator = self.fator(competencia)
        return None if fator is None else float(valor) * fator
