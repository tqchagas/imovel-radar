"""Validação cruzada da referência de ITBI: ela prevê a quitação que não viu?

Esconde 20% das quitações residenciais, constrói a escada de referência com os
80% restantes e tenta prever o R$/m² de cada linha escondida. É o que calibra
`EXACT_MIN_SAMPLE` e `STREET_MIN_SAMPLE`, e o que mostra se a dispersão da
amostra — o proxy de confiança que a nota usa — de fato prediz erro.

Não toca em portal nenhum: roda sobre a base de ITBI, em minutos.

    PYTHONPATH=. python scripts/validar_referencia.py

Medido em Belo Horizonte (set/2026, 8.148 linhas escondidas): erro mediano de
8,3% no tier de endereço exato, 18,4% na rua, 20,2% no bairro com faixa de área
e 22,8% no bairro amplo; e 5,1% / 11,7% / 18,1% conforme a dispersão da amostra
sobe de <15% para >30%, que valida o proxy da nota.
"""

import argparse
import random
from collections import defaultdict
from statistics import median

from sqlalchemy import select

from app.db.session import SessionLocal
from app.domain.opportunities import (
    AREA_MATCH_FACTOR, ListingInput, SaleIndex, is_valid_sale, sale_price_per_m2,
    select_reference, window_bounds,
)
from app.domain.slugs import address_key, street_key
from app.models.registry_address import RegistryAddress
from app.services.opportunities import fetch_reference_sales, latest_reference_date

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cidade", default="belo_horizonte")
parser.add_argument("--semente", type=int, default=20260902)
parser.add_argument(
    "--sem-cadastro", action="store_true",
    help="Ignora a dispersão de área do cadastro, medindo a escada como era antes dele.",
)
args = parser.parse_args()

random.seed(args.semente)
db = SessionLocal()
dia = latest_reference_date(db, args.cidade)
inicio, fim = window_bounds(dia)
todas = [s for s in fetch_reference_sales(db, args.cidade, inicio, fim) if is_valid_sale(s)]
# Dispersão das áreas do prédio: é ela que dispensa a janela de área no tier
# de endereço, então medir sem ela mede outra escada.
dispersoes = {}
if not args.sem_cadastro:
    for linha in db.execute(
        select(RegistryAddress).where(
            RegistryAddress.city == args.cidade, RegistryAddress.construction_type == "AP"
        )
    ).scalars():
        if linha.unit_area_dispersion is not None:
            dispersoes[(linha.street_key, linha.number_key)] = float(linha.unit_area_dispersion)
db.close()
print(f"prédios com dispersão de área conhecida: {len(dispersoes)}")

aps = [s for s in todas if (s.construction_type or "").strip().upper() == "AP"]
random.shuffle(aps)
corte = len(aps) // 5
escondidas, treino = aps[:corte], aps[corte:]
index = SaleIndex.build(treino, dia)
print(f"AP+RES na janela: {len(aps)} | treino={len(treino)} escondidas={len(escondidas)}")

erros_por_tier = defaultdict(list)
erros_por_amostra = defaultdict(list)
erros_por_dispersao = defaultdict(list)
sem_referencia = 0

for venda in escondidas:
    entrada = ListingInput(
        source="itbi", listing_id="x", tipo_imovel="APARTAMENTO",
        # select_reference converte a area do anuncio; desfaco para a janela
        # cair sobre a area construida desta propria linha.
        area_util_m2=float(venda.built_area_acquired) / AREA_MATCH_FACTOR,
        preco_total=float(venda.declared_value),
        bairro=venda.neighborhood, rua=venda.street, numero=venda.street_number,
        predio_dispersao_area=dispersoes.get(
            (street_key(venda.street), address_key(venda.street_number))
        ),
    )
    ref = select_reference(entrada, index, dia)
    if ref is None or ref.preco_m2_mediano <= 0:
        sem_referencia += 1
        continue
    real = sale_price_per_m2(venda)
    erro = abs(ref.preco_m2_mediano - real) / real
    erros_por_tier[ref.tipo_referencia].append(erro)
    faixa = ("1-4" if ref.amostra_count < 5 else "5-14" if ref.amostra_count < 15
             else "15-49" if ref.amostra_count < 50 else "50+")
    erros_por_amostra[faixa].append(erro)
    disp = ("baixa <15%" if ref.dispersao_relativa < 0.15
            else "media 15-30%" if ref.dispersao_relativa < 0.30 else "alta >30%")
    erros_por_dispersao[disp].append(erro)

def mostra(titulo, grupos, ordem=None):
    print(f"\n{titulo}")
    print(f"  {'grupo':16s} {'n':>6s} {'erro mediano':>13s} {'p75':>7s} {'p90':>7s} {'>40%':>7s}")
    chaves = ordem or sorted(grupos, key=lambda k: -len(grupos[k]))
    for chave in chaves:
        e = sorted(grupos.get(chave, []))
        if not e:
            continue
        n = len(e)
        print(f"  {chave:16s} {n:6d} {100*median(e):12.1f}% {100*e[3*n//4]:6.1f}% "
              f"{100*e[9*n//10]:6.1f}% {100*sum(1 for x in e if x > 0.4)/n:6.1f}%")

todos = [e for grupo in erros_por_tier.values() for e in grupo]
todos.sort()
print(f"\nerro mediano global: {100*median(todos):.1f}%  "
      f"(p75 {100*todos[3*len(todos)//4]:.1f}%, p90 {100*todos[9*len(todos)//10]:.1f}%, "
      f"n={len(todos)})")

mostra("erro por tier de referencia", erros_por_tier,
       ["endereco_exato", "rua", "bairro_area", "bairro_amplo"])
mostra("erro por tamanho da amostra", erros_por_amostra, ["1-4", "5-14", "15-49", "50+"])
mostra("erro por dispersao da amostra (o proxy que a nota usa)", erros_por_dispersao,
       ["baixa <15%", "media 15-30%", "alta >30%"])
print(f"\nsem referencia: {sem_referencia}")
