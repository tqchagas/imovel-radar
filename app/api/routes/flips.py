"""Estudos de flip: quanto custa reformar, o que sobra na venda, até quanto pagar.

O preview não grava nada — é o que a tela chama a cada mexida de campo. Quem
grava é o CRUD, que congela junto a cópia das premissas usadas.
"""

from fastapi import APIRouter

from app.domain.flip import Imovel, Negocio, Simulacao, simular
from app.domain.flip_premissas import Premissas, carregar_premissas
from app.schemas.flips import FlipEntradaIn, PremissaOut, SimulacaoOut

router = APIRouter(prefix="/flips", tags=["flip"])


def imovel_de(entrada: FlipEntradaIn) -> Imovel:
    return Imovel(
        area_seca_m2=entrada.area_seca_m2,
        banheiros=entrada.banheiros,
        cozinhas=entrada.cozinhas,
        portas=entrada.portas,
        eletrica_completa=entrada.eletrica_completa,
        hidraulica_completa_banheiro=entrada.hidraulica_completa_banheiro,
        hidraulica_completa_cozinha=entrada.hidraulica_completa_cozinha,
    )


def negocio_de(entrada: FlipEntradaIn) -> Negocio:
    return Negocio(
        preco_compra=entrada.preco_compra,
        arv_total=entrada.arv_total,
        meses_carrego=entrada.meses_carrego,
    )


def simulacao_out(simulacao: Simulacao) -> SimulacaoOut:
    return SimulacaoOut.model_validate(simulacao)


def simular_entrada(entrada: FlipEntradaIn, premissas: Premissas | None = None) -> SimulacaoOut:
    usadas = premissas or carregar_premissas()
    return simulacao_out(simular(imovel_de(entrada), negocio_de(entrada), usadas))


@router.post("/preview", response_model=SimulacaoOut)
def preview(payload: FlipEntradaIn) -> SimulacaoOut:
    """Calcula sem gravar. É o que o slider chama, com debounce na tela."""
    return simular_entrada(payload)


@router.get("/premissas", response_model=list[PremissaOut])
def premissas() -> list[PremissaOut]:
    return [PremissaOut.model_validate(item) for item in carregar_premissas().itens]
