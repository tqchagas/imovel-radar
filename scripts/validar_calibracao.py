"""Validação cruzada da calibração: ela prevê o preço pedido que não viu?

`validar_referencia.py` mede a escada de ITBI prevendo ITBI, e isso não diz
nada sobre a calibração — o fator que converte o R$/m² do cartório no R$/m² que
um anúncio comparável pediria. O fator só é falsificável contra anúncio, e é
isso que este script faz: esconde 20% dos anúncios ativos, mede a calibração
com os 80% restantes e tenta prever o preço pedido de cada anúncio escondido.

É o número que decide se acrescentar uma dimensão ao fator melhora ou só o
divide em células rasas. Sem ele, mexer na calibração é opinião.

    PYTHONPATH=. python scripts/validar_calibracao.py
    PYTHONPATH=. python scripts/validar_calibracao.py --sem-acabamento

Roda sobre o banco local, sem tocar em portal nenhum.
"""

import argparse
import random
from collections import defaultdict
from dataclasses import replace
from statistics import median

from sqlalchemy import select

from app.db.session import SessionLocal
from app.domain.buildings import BuildingIndex, buildings_from_rows
from app.domain.opportunities import (
    AREA_ORIGEM_INCERTA,
    SaleIndex,
    build_calibration,
    compute_opportunity,
    is_valid_sale,
    window_bounds,
)
from app.models.market_comparable import MarketComparable
from app.models.registry_address import RegistryAddress
from app.services.opportunities import (
    _listing_input,
    fetch_reference_sales,
    latest_reference_date,
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--cidade", default="belo_horizonte")
parser.add_argument("--semente", type=int, default=20260903)
parser.add_argument(
    "--sem-acabamento",
    action="store_true",
    help="Mede a calibração sem o padrão de acabamento do prédio.",
)
args = parser.parse_args()

random.seed(args.semente)
db = SessionLocal()
dia = latest_reference_date(db, args.cidade)
inicio, fim = window_bounds(dia)
vendas = [s for s in fetch_reference_sales(db, args.cidade, inicio, fim) if is_valid_sale(s)]
index = SaleIndex.build(vendas, dia)

predios = BuildingIndex.build(
    buildings_from_rows(
        db.execute(select(RegistryAddress).where(RegistryAddress.city == args.cidade))
        .scalars()
        .all()
    )
)
anuncios = (
    db.execute(
        select(MarketComparable).where(
            MarketComparable.cidade_normalizada == args.cidade,
            MarketComparable.ativo.is_(True),
            MarketComparable.area_util_m2 > 0,
            MarketComparable.preco_total > 0,
        )
    )
    .scalars()
    .all()
)
db.close()


def replace_finish(entrada):
    """A mesma entrada sem o padrão de acabamento, para medir a escada sem ele."""
    return replace(entrada, predio_padrao_acabamento=None)


entradas = []
for linha in anuncios:
    entrada = _listing_input(linha, None, predios)
    if entrada.area_origem == AREA_ORIGEM_INCERTA:
        # A área lida do texto do anúncio erra ~13% e para baixo; ela não entra
        # na calibração em produção e não pode entrar na medida dela.
        continue
    if args.sem_acabamento:
        entrada = replace_finish(entrada)
    entradas.append(entrada)

random.shuffle(entradas)
corte = len(entradas) // 5
escondidos, treino = entradas[:corte], entradas[corte:]
print(f"anúncios utilizáveis: {len(entradas)} | treino={len(treino)} escondidos={len(escondidos)}")

calibracao = build_calibration(treino, index)

erros_por_tier = defaultdict(list)
sem_estimativa = 0
for entrada in escondidos:
    oportunidade = compute_opportunity(entrada, index, dia, calibracao)
    if oportunidade is None or oportunidade.preco_estimado <= 0:
        sem_estimativa += 1
        continue
    real = entrada.preco_total
    erro = abs(oportunidade.preco_estimado_itbi - real) / real
    erros_por_tier[oportunidade.tipo_referencia].append(erro)

todos = sorted(e for grupo in erros_por_tier.values() for e in grupo)
if not todos:
    raise SystemExit("nenhuma estimativa produzida")

print(
    f"\nerro mediano global: {100 * median(todos):.1f}%  "
    f"(p75 {100 * todos[3 * len(todos) // 4]:.1f}%, "
    f"p90 {100 * todos[9 * len(todos) // 10]:.1f}%, n={len(todos)})"
)
print("\nerro por tier de referência")
print(f"  {'grupo':18s} {'n':>6s} {'erro mediano':>13s} {'p75':>7s} {'p90':>7s}")
for chave in ("endereco_exato", "endereco_geo", "rua", "bairro_area", "bairro_amplo"):
    e = sorted(erros_por_tier.get(chave, []))
    if not e:
        continue
    n = len(e)
    print(
        f"  {chave:18s} {n:6d} {100 * median(e):12.1f}% "
        f"{100 * e[3 * n // 4]:6.1f}% {100 * e[9 * n // 10]:6.1f}%"
    )
print(f"\nsem estimativa: {sem_estimativa}")
