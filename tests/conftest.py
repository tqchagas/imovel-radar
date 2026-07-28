import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.market_comparable import MarketComparable  # noqa: F401  (registers the table)
from app.models.transaction import Transaction  # noqa: F401  (registers the table)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
