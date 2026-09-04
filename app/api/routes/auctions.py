"""Imóveis de leilão digitados à mão, e o que o QuintoAndar diz sobre eles.

Nada aqui é coletado: o edital é lido por gente. A rota existe para guardar o
que foi digitado, chamar o portal e devolver as duas leituras lado a lado.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.auction_property import AuctionProperty
from app.schemas.auctions import (
    AuctionAppraisalOut,
    AuctionPropertyIn,
    AuctionPropertyOut,
    AuctionPropertyPatch,
    CoordinateSuggestionOut,
)
from app.services.appraisal import (
    FONTE_LABEL,
    FONTE_MANUAL,
    avaliar_imovel,
    sugerir_coordenada,
    ultima_avaliacao,
)

router = APIRouter(prefix="/auctions", tags=["leilao"])


def _saida(db: Session, imovel: AuctionProperty) -> AuctionPropertyOut:
    out = AuctionPropertyOut.model_validate(imovel)
    out.coordenada_rotulo = FONTE_LABEL.get(imovel.coordenada_fonte or "")
    avaliacao = ultima_avaliacao(db, imovel)
    if avaliacao is not None:
        out.avaliacao = AuctionAppraisalOut.model_validate(avaliacao)
    return out


def _buscar(db: Session, auction_id: int) -> AuctionProperty:
    imovel = db.get(AuctionProperty, auction_id)
    if imovel is None:
        raise HTTPException(status_code=404, detail="imóvel não encontrado")
    return imovel


@router.get("/coordenada", response_model=CoordinateSuggestionOut)
def sugerir(
    city: str = Query(...),
    street: str = Query(...),
    number: str | None = Query(None),
    db: Session = Depends(get_db),
) -> CoordinateSuggestionOut:
    """Uma sugestão de coordenada, para o dono confirmar.

    Só Belo Horizonte tem o diretório de condomínios e o cadastro carregados.
    Em qualquer outra cidade a resposta é 404, e o dono cola o ponto do mapa —
    inventar coordenada é o modo de falha que este desenho evita.
    """
    achado = sugerir_coordenada(db, city=city, street=street, number=number)
    if achado is None:
        raise HTTPException(
            status_code=404,
            detail="sem coordenada conhecida para este endereço; cole a do mapa",
        )
    lat, lon, fonte = achado
    return CoordinateSuggestionOut(
        latitude=lat, longitude=lon, fonte=fonte, rotulo=FONTE_LABEL[fonte]
    )


@router.get("", response_model=list[AuctionPropertyOut])
def listar(
    incluir_passados: bool = Query(False),
    db: Session = Depends(get_db),
) -> list[AuctionPropertyOut]:
    """Os imóveis ativos: sem data de leilão, ou com data ainda por vir.

    Passada a data a linha sai da lista, mas nada é apagado — ela continua no
    banco e volta com `incluir_passados`.
    """
    stmt = select(AuctionProperty)
    if not incluir_passados:
        stmt = stmt.where(
            (AuctionProperty.data_leilao.is_(None))
            | (AuctionProperty.data_leilao >= date.today())
        )
    stmt = stmt.order_by(
        AuctionProperty.data_leilao.is_(None), AuctionProperty.data_leilao.asc()
    )
    return [_saida(db, imovel) for imovel in db.execute(stmt).scalars()]


@router.post("", response_model=AuctionPropertyOut, status_code=201)
def criar(payload: AuctionPropertyIn, db: Session = Depends(get_db)) -> AuctionPropertyOut:
    dados = payload.model_dump()
    lat, lon = dados.pop("latitude"), dados.pop("longitude")
    fonte = FONTE_MANUAL

    if lat is None or lon is None:
        achado = sugerir_coordenada(
            db, city=payload.city, street=payload.address, number=payload.address_number
        )
        if achado is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "sem coordenada. Ela é o campo mais sensível desta conta — seis "
                    "metros já moveram a estimativa em 18%. Cole a do mapa."
                ),
            )
        lat, lon, fonte = achado

    imovel = AuctionProperty(**dados, latitude=lat, longitude=lon, coordenada_fonte=fonte)
    db.add(imovel)
    db.commit()
    db.refresh(imovel)
    return _saida(db, imovel)


@router.patch("/{auction_id}", response_model=AuctionPropertyOut)
def editar(
    auction_id: int, payload: AuctionPropertyPatch, db: Session = Depends(get_db)
) -> AuctionPropertyOut:
    imovel = _buscar(db, auction_id)
    mudancas = payload.model_dump(exclude_unset=True)
    if "latitude" in mudancas or "longitude" in mudancas:
        imovel.coordenada_fonte = FONTE_MANUAL
    for campo, valor in mudancas.items():
        setattr(imovel, campo, valor)
    db.commit()
    db.refresh(imovel)
    return _saida(db, imovel)


@router.delete("/{auction_id}", status_code=204)
def remover(auction_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_buscar(db, auction_id))
    db.commit()


@router.post("/{auction_id}/avaliar", response_model=AuctionAppraisalOut)
def avaliar(
    auction_id: int, force: bool = Query(False), db: Session = Depends(get_db)
) -> AuctionAppraisalOut:
    """Consulta o portal. Sem `force`, reaproveita uma leitura de até 30 dias."""
    registro = avaliar_imovel(db, _buscar(db, auction_id), force=force)
    return AuctionAppraisalOut.model_validate(registro)


@router.get("/{auction_id}/historico", response_model=list[AuctionAppraisalOut])
def historico(auction_id: int, db: Session = Depends(get_db)) -> list[AuctionAppraisalOut]:
    """As consultas anteriores, da mais recente para a mais antiga.

    É o que permite ver o número se mover conforme a data do leilão se aproxima.
    """
    imovel = _buscar(db, auction_id)
    return [AuctionAppraisalOut.model_validate(a) for a in imovel.avaliacoes]
