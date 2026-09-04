from datetime import date

from app.models.auction_property import AuctionAppraisal, AuctionProperty


def test_imovel_guarda_a_coordenada_com_a_fonte(db_session):
    """Seis metros de diferença moveram a estimativa em 18,4%; quem confia no
    número precisa saber de onde a coordenada veio."""
    db_session.add(
        AuctionProperty(
            apelido="Apto Funcionários",
            address="Rua Gonçalves Dias",
            address_number="865",
            neighborhood="Funcionários",
            city="Belo Horizonte",
            state="MG",
            latitude=-19.932468,
            longitude=-43.933033,
            coordenada_fonte="portal",
            total_area=295,
            bedroom_count=4,
            bathroom_count=3,
            suites_count=2,
            parking_slots=2,
            floor=8,
            condominium_per_month=1500,
            iptu_per_year=4800,
            data_leilao=date(2026, 10, 12),
            lance_minimo=620000,
        )
    )
    db_session.commit()

    gravado = db_session.query(AuctionProperty).one()
    assert gravado.coordenada_fonte == "portal"
    assert float(gravado.total_area) == 295
    assert gravado.data_leilao == date(2026, 10, 12)


def test_avaliacoes_ficam_em_historico_e_caem_com_o_imovel(db_session):
    """O dono reconsulta antes do leilão; sobrescrever apagaria o movimento."""
    imovel = AuctionProperty(
        address="Rua X", city="Belo Horizonte", latitude=-19.9, longitude=-43.9, total_area=100
    )
    imovel.avaliacoes.append(
        AuctionAppraisal(preco_qpreco=1_000_000, certeza="low", comparaveis_usados=5)
    )
    imovel.avaliacoes.append(
        AuctionAppraisal(preco_qpreco=1_100_000, certeza="medium", comparaveis_usados=6)
    )
    db_session.add(imovel)
    db_session.commit()

    assert db_session.query(AuctionAppraisal).count() == 2

    db_session.delete(imovel)
    db_session.commit()
    assert db_session.query(AuctionAppraisal).count() == 0


def test_comparaveis_ausentes_viram_null_de_verdade(db_session):
    imovel = AuctionProperty(
        address="Rua X", city="Belo Horizonte", latitude=-19.9, longitude=-43.9, total_area=100
    )
    imovel.avaliacoes.append(AuctionAppraisal(preco_qpreco=1_000_000, comparaveis_json=None))
    db_session.add(imovel)
    db_session.commit()

    from sqlalchemy import func, select

    nulos = db_session.scalar(
        select(func.count()).select_from(AuctionAppraisal).where(
            AuctionAppraisal.comparaveis_json.is_(None)
        )
    )
    assert nulos == 1
