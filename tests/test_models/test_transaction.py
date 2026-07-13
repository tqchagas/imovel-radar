from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.transaction import Transaction


def test_transaction_table_created_and_insertable() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Transaction(
                city="belo_horizonte",
                source_row_hash="abc123",
                raw_address="RUA TESTE 1 - CENTRO - 30000-000 - BELO HORIZONTE - MG",
                street="RUA TESTE",
                street_number="1",
                complement=None,
                postal_code="30000-000",
                neighborhood="CENTRO",
                construction_year=2000,
                land_area=100.0,
                built_area_acquired=80.0,
                acquired_area_total=80.0,
                finish_standard="P3",
                acquired_fraction=1.0,
                construction_type="AP",
                occupation_type="RESIDENCIAL",
                declared_value=200000.0,
                calc_base_value=200000.0,
                zoning="ZA",
                settlement_date=date(2026, 6, 1),
            )
        )
        session.commit()

        result = session.query(Transaction).one()
        assert result.city == "belo_horizonte"
        assert result.neighborhood == "CENTRO"
