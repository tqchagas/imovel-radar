"""Mede AREA_MATCH_FACTOR: quanto a área do ITBI excede a área anunciada.

O cartório lança "Área Construída Adquirida" — área de construção da unidade
vezes o percentual adquirido — e o portal anuncia área útil. As duas não medem
a mesma coisa, então a janela de comparação por área precisa ser convertida.

A medida só é possível onde as duas pontas apontam para o mesmo endereço, o que
exige o número da rua: hoje só o VivaReal o publica. Rode depois de uma coleta,
e a cada cidade nova:

    PYTHONPATH=. python scripts/medir_area_itbi.py --cidade "Belo Horizonte"
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from statistics import median

from sqlalchemy import text

from app.db.session import SessionLocal
from app.domain.opportunities import AREA_MATCH_FACTOR, RESIDENTIAL_OCCUPATION
from app.domain.slugs import address_key

MIN_ITBI_NO_ENDERECO = 3
MIN_PARES_POR_BAIRRO = 10

ITBI_SQL = """
    SELECT neighborhood, street, street_number, built_area_acquired
    FROM transactions
    WHERE city = :cidade
      AND upper(trim(occupation_type)) = :residencial
      AND upper(trim(construction_type)) = 'AP'
      AND declared_value > 0 AND built_area_acquired > 0
      AND settlement_date >= (
          SELECT max(settlement_date) - interval '24 months'
          FROM transactions WHERE city = :cidade
      )
"""

ANUNCIOS_SQL = """
    SELECT source, bairro_normalizado, rua_normalizada, numero_normalizado, area_util_m2
    FROM market_comparables
    WHERE ativo AND cidade_normalizada = :cidade
      AND area_util_m2 > 0 AND numero_normalizado IS NOT NULL
      AND upper(tipo_imovel) = 'APARTAMENTO'
"""


def _percentil(ordenados: list[float], fracao: float) -> float:
    return ordenados[min(len(ordenados) - 1, int(fracao * len(ordenados)))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cidade", default="Belo Horizonte")
    args = parser.parse_args()
    cidade = address_key(args.cidade)

    db = SessionLocal()
    try:
        por_endereco: dict[tuple, list[float]] = defaultdict(list)
        rows = db.execute(
            text(ITBI_SQL), {"cidade": cidade, "residencial": RESIDENTIAL_OCCUPATION}
        ).all()
        for bairro, rua, numero, area in rows:
            chave = (address_key(bairro), address_key(rua), address_key(numero))
            if all(chave):
                por_endereco[chave].append(float(area))

        razoes: list[float] = []
        por_bairro: dict[str, list[float]] = defaultdict(list)
        for _source, bairro, rua, numero, area in db.execute(
            text(ANUNCIOS_SQL), {"cidade": cidade}
        ).all():
            amostra = por_endereco.get((address_key(bairro), address_key(rua), address_key(numero)))
            if not amostra or len(amostra) < MIN_ITBI_NO_ENDERECO:
                continue
            razao = median(amostra) / float(area)
            razoes.append(razao)
            por_bairro[address_key(bairro)].append(razao)
    finally:
        db.close()

    if not razoes:
        print(f"Nenhum par medido em {args.cidade}. Só fontes com número da rua servem.")
        return

    razoes.sort()
    print(f"{args.cidade}: {len(razoes)} pares (anúncio x ITBI no mesmo endereço)")
    print(f"  p25={_percentil(razoes, 0.25):.2f}  mediana={median(razoes):.2f}  "
          f"p75={_percentil(razoes, 0.75):.2f}")
    print(f"  AREA_MATCH_FACTOR em uso: {AREA_MATCH_FACTOR}")

    densos = {b: median(v) for b, v in por_bairro.items() if len(v) >= MIN_PARES_POR_BAIRRO}
    print(f"\nbairros com >= {MIN_PARES_POR_BAIRRO} pares: {len(densos)}")
    for bairro, valor in sorted(densos.items(), key=lambda kv: -kv[1]):
        print(f"  {bairro:30s} {valor:.2f}  (n={len(por_bairro[bairro])})")


if __name__ == "__main__":
    main()
