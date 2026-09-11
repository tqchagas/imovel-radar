"""Estudos de flip: quanto custa reformar, o que sobra na venda, até quanto pagar.

O preview não grava nada — é o que a tela chama a cada mexida de campo. Quem
grava é o CRUD, que congela junto a cópia das premissas usadas.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.flip import Imovel, Negocio, Simulacao, simular
from app.domain.flip_premissas import Premissas, carregar_premissas
from app.models.flip_study import FlipStudy
from app.schemas.flips import (
    FlipEntradaIn,
    FlipStudyIn,
    FlipStudyListItem,
    FlipStudyOut,
    FlipStudyPatch,
    PremissaOut,
    SimulacaoOut,
)
from app.services import flip_studies

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


def _estudo_out(estudo: FlipStudy) -> FlipStudyOut:
    # A simulação não é coluna; montar campo a campo evita um `model_validate`
    # que reclamaria dela como obrigatória e ausente.
    campos = {
        campo: getattr(estudo, campo)
        for campo in FlipStudyOut.model_fields
        if campo != "simulacao"
    }
    return FlipStudyOut(**campos, simulacao=simulacao_out(flip_studies.simulacao_do(estudo)))


def _linha(estudo: FlipStudy) -> FlipStudyListItem:
    simulacao = flip_studies.simulacao_do(estudo)
    return FlipStudyListItem(
        id=estudo.id,
        apelido=estudo.apelido,
        endereco=estudo.endereco,
        bairro=estudo.bairro,
        status=estudo.status,
        area_util_m2=float(estudo.area_util_m2),
        preco_compra=float(estudo.preco_compra),
        arv_total=float(estudo.arv_total),
        meses_carrego=estudo.meses_carrego,
        obra_total=simulacao.orcamento.total,
        capital_empatado=simulacao.dre.capital_empatado,
        lucro_liquido=simulacao.dre.lucro_liquido,
        roi=simulacao.dre.roi,
        tir_anual=simulacao.dre.tir_anual,
        mao=simulacao.mao,
    )


def _buscar(db: Session, flip_id: int) -> FlipStudy:
    estudo = flip_studies.buscar(db, flip_id)
    if estudo is None:
        raise HTTPException(status_code=404, detail="estudo não encontrado")
    return estudo


@router.get("", response_model=list[FlipStudyListItem])
def listar(
    bairro: str | None = Query(None),
    status: str | None = Query(None),
    preco_min: float | None = Query(None),
    preco_max: float | None = Query(None),
    db: Session = Depends(get_db),
) -> list[FlipStudyListItem]:
    return [
        _linha(estudo) for estudo in flip_studies.listar(db, bairro, status, preco_min, preco_max)
    ]


@router.post("", response_model=FlipStudyOut, status_code=201)
def criar(payload: FlipStudyIn, db: Session = Depends(get_db)) -> FlipStudyOut:
    return _estudo_out(flip_studies.criar(db, payload))


@router.get("/{flip_id}", response_model=FlipStudyOut)
def detalhe(flip_id: int, db: Session = Depends(get_db)) -> FlipStudyOut:
    return _estudo_out(_buscar(db, flip_id))


@router.patch("/{flip_id}", response_model=FlipStudyOut)
def editar(flip_id: int, payload: FlipStudyPatch, db: Session = Depends(get_db)) -> FlipStudyOut:
    estudo = _buscar(db, flip_id)
    mudancas = payload.model_dump(exclude_unset=True)
    atualizar = bool(mudancas.pop("atualizar_premissas", False))
    return _estudo_out(flip_studies.editar(db, estudo, mudancas, atualizar))


@router.delete("/{flip_id}", status_code=204)
def remover(flip_id: int, db: Session = Depends(get_db)) -> None:
    flip_studies.remover(db, _buscar(db, flip_id))
