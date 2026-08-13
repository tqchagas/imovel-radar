from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.transaction import Transaction
from app.services.market_data import fetch_sales, reference_date


def test_market_data_service_reads_reference_and_scoped_sales() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            Transaction(
                city="belo_horizonte",
                source_row_hash="service-hash",
                raw_address="RUA A 1",
                street="RUA A",
                street_number="1",
                neighborhood="SAVASSI",
                declared_value=100,
                calc_base_value=100,
                built_area_acquired=50,
                settlement_date=date(2025, 1, 1),
            )
        )
        db.commit()

        assert reference_date(db, "belo_horizonte") == date(2025, 1, 1)
        sales = fetch_sales(
            db,
            "belo_horizonte",
            start=date(2024, 1, 1),
            end=date(2025, 1, 1),
        )

    assert len(sales) == 1
    assert sales[0].street_number == "1"
