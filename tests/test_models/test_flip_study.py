import pytest
from sqlalchemy.exc import IntegrityError

from app.models.flip_study import FlipStudy


def _estudo(**ajustes) -> FlipStudy:
    dados = dict(
        apelido="Apto Lourdes",
        endereco="Rua Alvarenga Peixoto, 1420",
        bairro="Lourdes",
        cidade="belo_horizonte",
        area_util_m2=92.0,
        area_seca_m2=92.0,
        quartos=3,
        banheiros=2,
        cozinhas=1,
        portas=6,
        preco_compra=680000.0,
        arv_total=1080000.0,
        meses_carrego=7,
        status="oportunidade",
        origem="manual",
        premissas_json="{}",
    )
    dados.update(ajustes)
    return FlipStudy(**dados)


def test_grava_e_le_um_estudo(db_session) -> None:
    db_session.add(_estudo())
    db_session.commit()
    salvo = db_session.query(FlipStudy).one()
    assert salvo.bairro == "Lourdes"
    assert float(salvo.preco_compra) == 680000.0
    assert salvo.eletrica_completa is False


def test_status_invalido_e_recusado(db_session) -> None:
    db_session.add(_estudo(status="talvez"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_origem_invalida_e_recusada(db_session) -> None:
    db_session.add(_estudo(origem="planilha"))
    with pytest.raises(IntegrityError):
        db_session.commit()
