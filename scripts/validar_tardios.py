"""Tirar o registro tardio da referência melhora a previsão da venda de mercado?

Mesma validação cruzada de `validar_referencia.py` — esconde 20% das quitações
de apartamento residencial da janela, monta a escada de referência com o resto
e prevê o R$/m² das escondidas —, repetida para cada variante da regra de
`app.domain.late_registration`. Nada é gravado: as variantes são calculadas
aqui, sobre a base inteira da cidade.

Para as variantes serem comparáveis, todas preveem o mesmo conjunto: as
escondidas que nenhuma variante marca, ou seja, vendas de mercado para qualquer
uma delas. O que muda de uma para outra é só o que sai do treino.

    PYTHONPATH=. python scripts/validar_tardios.py

Medido em Belo Horizonte (set/2026, janela 2024-06..2026-06, três sementes,
4.936 previsões em prédios com marca): sem tirar nada, erro mediano de 10,46% e
viés de -2,60%; com a regra atual (revenda 0,90), 9,97% e -1,19%. Lançamento
sozinho: 9,99% marcando 10.167 em vez de 8.251. Só confiança alta: 10,06%. Na
base inteira o efeito é pequeno (12,50% -> 12,35%): a marca é 2-3% da janela.
"""

import argparse
import random
from collections import defaultdict
from dataclasses import replace
from statistics import median

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.domain.late_registration import DEFAULT_RULE, Settlement, flag_late_registrations
from app.domain.market_stats import Sale
from app.domain.opportunities import (
    AREA_MATCH_FACTOR, RESIDENTIAL_OCCUPATION, ListingInput, SaleIndex, is_valid_sale,
    sale_price_per_m2, select_reference, window_bounds,
)
from app.domain.slugs import address_key, street_key
from app.models.registry_address import RegistryAddress
from app.models.transaction import Transaction

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cidade", default="belo_horizonte")
parser.add_argument("--sementes", type=int, nargs="+", default=[20260919, 1, 2])
args = parser.parse_args()

# Cada variante: (nome, regra, confianças que saem do treino).
SEM_REVENDA = replace(DEFAULT_RULE, max_resale_price_ratio=None)
VARIANTES = [
    ("nenhuma", None, set()),
    ("lançamento+base (v2)", SEM_REVENDA, {"alta", "media"}),
    ("revenda 0,85", replace(DEFAULT_RULE, max_resale_price_ratio=0.85), {"alta", "media"}),
    ("revenda 0,90", DEFAULT_RULE, {"alta", "media"}),
    ("revenda 0,95", replace(DEFAULT_RULE, max_resale_price_ratio=0.95), {"alta", "media"}),
    ("revenda 0,90 só alta", DEFAULT_RULE, {"alta"}),
]

db = SessionLocal()
cobertura = db.scalar(
    select(func.min(Transaction.settlement_date)).where(Transaction.city == args.cidade)
)
predios = [
    Settlement(
        id=r.id, street=r.street, street_number=r.street_number, complement=r.complement,
        settlement_date=r.settlement_date, declared_value=float(r.declared_value),
        calc_base_value=float(r.calc_base_value),
        built_area_acquired=float(r.built_area_acquired) if r.built_area_acquired else None,
        construction_year=r.construction_year, construction_type=r.construction_type,
    )
    for r in db.execute(
        select(Transaction).where(
            Transaction.city == args.cidade,
            Transaction.street_number.is_not(None),
            Transaction.complement.is_not(None),
        )
    ).scalars()
]

# A janela vem da quitação mais recente, marcada ou não: é a mesma para todas.
dia = db.scalar(
    select(func.max(Transaction.settlement_date)).where(
        Transaction.city == args.cidade,
        func.upper(Transaction.occupation_type) == RESIDENTIAL_OCCUPATION,
    )
)
inicio, fim = window_bounds(dia)
janela = [
    Sale(
        neighborhood=r.neighborhood, street=r.street, street_number=r.street_number,
        settlement_date=r.settlement_date, declared_value=float(r.declared_value),
        built_area_acquired=float(r.built_area_acquired) if r.built_area_acquired else None,
        construction_type=r.construction_type, occupation_type=r.occupation_type,
        transaction_id=r.id,
    )
    for r in db.execute(
        select(Transaction).where(
            Transaction.city == args.cidade,
            Transaction.settlement_date >= inicio,
            Transaction.settlement_date <= fim,
        )
    ).scalars()
]
janela = [s for s in janela if is_valid_sale(s)]
dispersoes = {
    (linha.street_key, linha.number_key): float(linha.unit_area_dispersion)
    for linha in db.execute(
        select(RegistryAddress).where(
            RegistryAddress.city == args.cidade, RegistryAddress.construction_type == "AP"
        )
    ).scalars()
    if linha.unit_area_dispersion is not None
}
db.close()

marcadas = {
    nome: (
        {i for i, c in flag_late_registrations(predios, coverage_start=cobertura, rule=regra).items()
         if c in saem}
        if regra else set()
    )
    for nome, regra, saem in VARIANTES
}
todas_marcadas = set().union(*marcadas.values())

aps = sorted(
    (s for s in janela if (s.construction_type or "").strip().upper() == "AP"),
    key=lambda s: s.transaction_id,
)
# Prédios com alguma quitação marcada por alguma variante: é onde a marca muda
# a referência de endereço exato, e onde o efeito dela aparece sem diluir.
por_id = {s.id: s for s in predios}
afetados = {
    (street_key(por_id[i].street), address_key(por_id[i].street_number))
    for i in todas_marcadas
}


def predio(venda):
    return (street_key(venda.street), address_key(venda.street_number))


def avaliar(treino, escondidas):
    index = SaleIndex.build(treino, dia)
    erros = []
    for venda in escondidas:
        entrada = ListingInput(
            source="itbi", listing_id="x", tipo_imovel="APARTAMENTO",
            area_util_m2=float(venda.built_area_acquired) / AREA_MATCH_FACTOR,
            preco_total=float(venda.declared_value),
            bairro=venda.neighborhood, rua=venda.street, numero=venda.street_number,
            predio_dispersao_area=dispersoes.get(predio(venda)),
        )
        ref = select_reference(entrada, index, dia)
        if ref is None or ref.preco_m2_mediano <= 0:
            continue
        real = sale_price_per_m2(venda)
        # Com sinal: o registro tardio puxa a referência para baixo, então o
        # viés mostra de que lado o erro está.
        erros.append(((ref.preco_m2_mediano - real) / real, predio(venda) in afetados))
    return erros


resultados = defaultdict(lambda: defaultdict(list))
for semente in args.sementes:
    random.seed(semente)
    embaralhadas = aps[:]
    random.shuffle(embaralhadas)
    corte = len(embaralhadas) // 5
    escondidas = [s for s in embaralhadas[:corte] if s.transaction_id not in todas_marcadas]
    for nome, _regra, _saem in VARIANTES:
        fora = marcadas[nome]
        treino = [s for s in embaralhadas[corte:] if s.transaction_id not in fora]
        for erro, afetado in avaliar(treino, escondidas):
            resultados[nome]["todas"].append(erro)
            if afetado:
                resultados[nome]["afetados"].append(erro)

print(f"janela {inicio}..{fim} | AP+RES {len(aps)} | sementes {args.sementes}")
print(f"\n{'variante':22s} {'fora':>6s} | {'todas: mediano':>14s} {'viés':>7s} | "
      f"{'prédios afetados: n':>19s} {'mediano':>8s} {'viés':>7s}")
for nome, _regra, _saem in VARIANTES:
    t = resultados[nome]["todas"]
    a = resultados[nome]["afetados"]
    print(
        f"{nome:22s} {len(marcadas[nome]):6d} | {100*median(abs(e) for e in t):13.2f}% "
        f"{100*median(t):+6.2f}% | {len(a):19d} {100*median(abs(e) for e in a):7.2f}% "
        f"{100*median(a):+6.2f}%"
    )
