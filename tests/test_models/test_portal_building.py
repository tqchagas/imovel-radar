from datetime import date

from app.models.portal_building import PortalBuilding


def test_portal_building_guarda_o_endereco_e_as_instalacoes(db_session):
    """É o número que o anúncio não publica, e é por ele que a escada de
    referência alcança o tier de endereço exato."""
    db_session.add(
        PortalBuilding(
            source="quintoandar",
            external_id="1d47sjeomd",
            slug="rua-professor-moraes-444-funcionarios-belo-horizonte",
            url="https://www.quintoandar.com.br/condominio/x-1d47sjeomd",
            city="belo_horizonte",
            street="Rua Professor Moraes",
            street_number="444",
            street_key="rua_professor_moraes",
            number_key="444",
            postal_code="30150-370",
            neighborhood="Funcionários",
            lat=-19.937088,
            lon=-43.931404,
            min_area=27,
            max_area=58,
            min_bedrooms=1,
            max_bedrooms=2,
            installations=["ELEVADOR", "PORTARIA_24H"],
            doorman="NightAndDayShift",
            source_lastmod=date(2026, 9, 3),
        )
    )
    db_session.commit()

    gravado = db_session.query(PortalBuilding).one()
    assert gravado.street_key == "rua_professor_moraes"
    assert gravado.number_key == "444"
    assert gravado.installations == ["ELEVADOR", "PORTARIA_24H"]
    assert gravado.source_lastmod == date(2026, 9, 3)


def test_lista_ausente_vira_null_de_verdade(db_session):
    """`sa.JSON` grava Python None como JSON `null` por padrão, e aí a coluna
    deixa de ser nula para o banco — `count()` e `is null` passam a mentir."""
    db_session.add(
        PortalBuilding(
            source="quintoandar",
            external_id="semnada00",
            url="https://q/x",
            city="belo_horizonte",
            street_key="rua_x",
            number_key="1",
            installations=None,
        )
    )
    db_session.commit()

    from sqlalchemy import func, select

    achados = db_session.scalar(
        select(func.count()).select_from(PortalBuilding).where(
            PortalBuilding.installations.is_(None)
        )
    )
    assert achados == 1
