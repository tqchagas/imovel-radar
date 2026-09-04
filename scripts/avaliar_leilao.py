"""Quanto o QuintoAndar diz que este imóvel vale.

Uso mínimo, em Belo Horizonte (a coordenada é resolvida sozinha):

    PYTHONPATH=. python scripts/avaliar_leilao.py \\
        --rua "Rua Gonçalves Dias" --numero 865 --cidade "Belo Horizonte" \\
        --area 295 --quartos 4 --banheiros 3 --vagas 2

Fora de Belo Horizonte, a coordenada é obrigatória e vem do mapa:

    ... --cidade "São Paulo" --uf SP --lat -23.5546 --lon -46.6906

Coordenada errada não dá erro: o portal devolve um número plausível do
quarteirão vizinho. Por isso ela é sempre impressa, para conferência.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.core.http_client import PortalBlocked
from app.db.session import SessionLocal
from app.domain.slugs import address_key, street_key
from app.models.portal_building import PortalBuilding
from app.models.registry_address import RegistryAddress
from app.domain.appraisal import MIN_COMPARAVEIS, avaliar, comparaveis_uteis
from app.pricing.qpreco_calculadora import (
    EstimateInput,
    QprecoUnavailable,
    fetch_comparables,
    fetch_estimate,
)

FONTE_PORTAL = "diretório de condomínios do portal"
FONTE_CADASTRO = "cadastro imobiliário da prefeitura"
FONTE_VOCE = "informada por você"


def coordenada_do_cadastro(db, cidade: str, rua: str, numero: str | None):
    """A coordenada do prédio, quando alguma base local conhece o endereço.

    O diretório de condomínios do portal fica a 1 m do anúncio na mediana e o
    lote do cadastro da prefeitura a 8 m — as duas melhores que existem sem
    alguém abrir o mapa. Só Belo Horizonte tem as duas carregadas.
    """
    chave_rua, chave_numero = street_key(rua), address_key(numero)
    if not chave_rua or not chave_numero or address_key(cidade) != "belo_horizonte":
        return None, None, None

    predio = db.execute(
        select(PortalBuilding.lat, PortalBuilding.lon)
        .where(PortalBuilding.city == "belo_horizonte")
        .where(PortalBuilding.street_key == chave_rua)
        .where(PortalBuilding.number_key == chave_numero)
        .where(PortalBuilding.lat.is_not(None))
    ).first()
    if predio:
        return float(predio[0]), float(predio[1]), FONTE_PORTAL

    lote = db.execute(
        select(RegistryAddress.lat, RegistryAddress.lon)
        .where(RegistryAddress.city == "belo_horizonte")
        .where(RegistryAddress.street_key == chave_rua)
        .where(RegistryAddress.number_key == chave_numero)
        .where(RegistryAddress.lat.is_not(None))
    ).first()
    if lote:
        return float(lote[0]), float(lote[1]), FONTE_CADASTRO
    return None, None, None



def _reais(valor) -> str:
    if valor is None:
        return "—"
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rua", required=True)
    p.add_argument("--numero")
    p.add_argument("--bairro")
    p.add_argument("--cidade", required=True)
    p.add_argument("--uf")
    p.add_argument("--area", type=float, required=True, help="Área ÚTIL, em m².")
    p.add_argument("--quartos", type=int, default=2)
    p.add_argument("--banheiros", type=int, default=1)
    p.add_argument("--suites", type=int, default=0)
    p.add_argument("--vagas", type=int, default=0)
    p.add_argument("--andar", type=int)
    p.add_argument("--condominio", type=float, default=0)
    p.add_argument("--iptu", type=float, default=0, help="IPTU anual.")
    p.add_argument("--tipo", default="APARTMENT", choices=["APARTMENT", "HOUSE"])
    p.add_argument("--lat", type=float)
    p.add_argument("--lon", type=float)
    args = p.parse_args()

    lat, lon, fonte = args.lat, args.lon, FONTE_VOCE
    if lat is None or lon is None:
        db = SessionLocal()
        try:
            achado = coordenada_do_cadastro(db, args.cidade, args.rua, args.numero)
        finally:
            db.close()
        if achado and achado[0] is not None:
            lat, lon, fonte = achado
    if lat is None or lon is None:
        raise SystemExit(
            "Sem coordenada. Em Belo Horizonte ela sai de rua+número; fora dali,\n"
            "passe --lat e --lon (abra o endereço no Google Maps, confira o pino\n"
            "no prédio certo e copie). O portal NÃO acusa coordenada errada — ele\n"
            "devolve o valor do quarteirão vizinho."
        )

    entrada = EstimateInput(
        address=args.rua,
        address_number=int(args.numero) if args.numero and args.numero.isdigit() else None,
        neighborhood=args.bairro,
        city=args.cidade,
        state=args.uf,
        latitude=lat,
        longitude=lon,
        house_type=args.tipo,
        total_area=args.area,
        bedroom_count=args.quartos,
        bathroom_count=args.banheiros,
        suites_count=args.suites,
        parking_slots=args.vagas,
        floor=args.andar,
        condominium_per_month=args.condominio,
        iptu_per_year=args.iptu,
    )

    endereco = f"{args.rua}{', ' + args.numero if args.numero else ''} — {args.cidade}"
    print(f"\n{endereco}")
    print(f"{args.area:.0f} m² úteis · {args.quartos} quartos · {args.vagas} vagas")
    print(f"coordenada {lat:.6f}, {lon:.6f}  ({fonte})")
    if fonte != FONTE_PORTAL:
        # Medido: o mesmo imóvel, com dois pontos separados por seis metros,
        # devolve 4.513.000 e 3.681.000 — 18,4% de diferença, de forma
        # determinística. A coordenada é o campo mais sensível que existe aqui,
        # e a que o modelo espera é a que o próprio portal publica para o
        # prédio, não o centróide do lote da prefeitura.
        print(
            "  ⚠ esta coordenada NÃO é a que o QuintoAndar usa para o prédio.\n"
            "    Seis metros de diferença já moveram 18% numa medida. Rode\n"
            "    `make condominios` para cobrir mais prédios, ou passe --lat/--lon\n"
            "    do ponto que o portal mostra."
        )
    print()

    try:
        est = fetch_estimate(entrada)
    except QprecoUnavailable as erro:
        raise SystemExit(f"Estimativa indisponível: {erro}")
    except PortalBlocked as erro:
        raise SystemExit(f"O portal recusou ({erro}). Não repita agora.")

    m2 = est.suggested_price / args.area
    print(f"  VALOR QUINTOANDAR      {_reais(est.suggested_price)}   ({_reais(m2)}/m²)")
    print(f"  predictionCertainty    {est.certainty}")
    # Os rótulos são os do portal: lá o destaque "Venda por / Ideal" é o MENOR
    # dos três, e "na média dos similares" é o maior.
    print(f"  ideal (venda por)      {_reais(est.lower_bound)}")
    print(f"  média dos similares    {_reais(est.upper_bound)}")
    print(f"  extremos do modelo     {_reais(est.limit_lower)} a {_reais(est.limit_upper)}")

    try:
        comps = fetch_comparables(entrada, est)
    except (PortalBlocked, RuntimeError) as erro:
        print(f"\n  (comparáveis indisponíveis: {erro})")
        return

    leitura = avaliar(est, comps.sold, area=args.area, quartos=args.quartos)
    uteis = comparaveis_uteis(comps.sold, area=args.area, quartos=args.quartos)
    print(f"\n  vendidos no entorno    {len(comps.sold)} (dos quais {len(uteis)} comparáveis)")
    if comps.days_until_deal:
        print(f"  dias até fechar        {comps.days_until_deal}")

    if leitura.preco_vendidos is not None:
        marca = "  <-- ATÍPICO, olhe os comparáveis" if leitura.atipico else ""
        print(f"  mediana dos vendidos   {_reais(leitura.preco_vendidos)}")
        print(f"  divergência            {leitura.divergencia_pct * 100:+.1f}%{marca}")
    else:
        print(f"  mediana dos vendidos   — (menos de {MIN_COMPARAVEIS} comparáveis)")

    if comps.sold:
        print("\n  vendas usadas na conta:" if uteis else "\n  vendas no entorno (nenhuma comparável):")
        for c in (uteis or list(comps.sold)[:6]):
            quando = c.sold_at.strftime("%Y-%m") if c.sold_at else "  —   "
            dist = f"{c.distance_km * 1000:>5.0f}m" if c.distance_km is not None else "    —"
            quartos = f"{c.bedroom_count}q" if c.bedroom_count is not None else "－"
            condo = " [mesmo condomínio]" if c.same_condo else ""
            print(
                f"    {quando}  {_reais(c.price):>14}  {_reais(c.price_m2):>11}/m²  "
                f"{c.total_area:>5.0f}m² {quartos:>3}  {dist}  {c.address or ''}{condo}"
            )
    print()


if __name__ == "__main__":
    main()
