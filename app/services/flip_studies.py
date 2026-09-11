"""Estudos de flip no banco: gravar, listar, e recalcular com as premissas certas.

A conta mora em `app.domain.flip`. Aqui só entram as decisões que dependem de
persistência — em especial qual tabela de preços usar: a do estudo, e não a do
arquivo, salvo quando o dono pedir para atualizar.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.flip import Imovel, Negocio, Simulacao, simular
from app.domain.flip_premissas import Premissas, carregar_premissas, premissas_de_valores
from app.models.flip_study import FlipStudy
from app.schemas.flips import FlipStudyIn


def premissas_do(estudo: FlipStudy) -> Premissas:
    valores = json.loads(estudo.premissas_json or "{}")
    # Estudo anterior ao snapshot, ou snapshot corrompido: cai para o arquivo
    # atual, que é melhor que quebrar a listagem inteira.
    return premissas_de_valores(valores) if valores else carregar_premissas()


def _imovel(estudo: FlipStudy) -> Imovel:
    return Imovel(
        area_seca_m2=float(estudo.area_seca_m2),
        banheiros=estudo.banheiros,
        cozinhas=estudo.cozinhas,
        portas=estudo.portas,
        eletrica_completa=estudo.eletrica_completa,
        hidraulica_completa_banheiro=estudo.hidraulica_completa_banheiro,
        hidraulica_completa_cozinha=estudo.hidraulica_completa_cozinha,
    )


def _negocio(estudo: FlipStudy) -> Negocio:
    return Negocio(
        preco_compra=float(estudo.preco_compra),
        arv_total=float(estudo.arv_total),
        meses_carrego=estudo.meses_carrego,
    )


def simulacao_do(estudo: FlipStudy) -> Simulacao:
    return simular(_imovel(estudo), _negocio(estudo), premissas_do(estudo))


def criar(db: Session, payload: FlipStudyIn) -> FlipStudy:
    premissas = carregar_premissas()
    estudo = FlipStudy(
        **payload.model_dump(),
        premissas_json=json.dumps(premissas.como_valores()),
    )
    db.add(estudo)
    db.commit()
    db.refresh(estudo)
    return estudo


def buscar(db: Session, flip_id: int) -> FlipStudy | None:
    return db.get(FlipStudy, flip_id)


def listar(
    db: Session,
    bairro: str | None = None,
    status: str | None = None,
    preco_min: float | None = None,
    preco_max: float | None = None,
) -> list[FlipStudy]:
    stmt = select(FlipStudy)
    if bairro:
        stmt = stmt.where(FlipStudy.bairro == bairro)
    if status:
        stmt = stmt.where(FlipStudy.status == status)
    if preco_min is not None:
        stmt = stmt.where(FlipStudy.preco_compra >= preco_min)
    if preco_max is not None:
        stmt = stmt.where(FlipStudy.preco_compra <= preco_max)
    stmt = stmt.order_by(FlipStudy.created_at.desc(), FlipStudy.id.desc())
    return list(db.execute(stmt).scalars())


def editar(
    db: Session, estudo: FlipStudy, mudancas: dict, atualizar_premissas: bool = False
) -> FlipStudy:
    for campo, valor in mudancas.items():
        setattr(estudo, campo, valor)
    if atualizar_premissas:
        estudo.premissas_json = json.dumps(carregar_premissas().como_valores())
    db.commit()
    db.refresh(estudo)
    return estudo


def remover(db: Session, estudo: FlipStudy) -> None:
    db.delete(estudo)
    db.commit()
