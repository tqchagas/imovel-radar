import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.listing_price_event import ListingPriceEvent  # noqa: F401
from app.models.market_comparable import MarketComparable  # noqa: F401  (registers the table)
from app.models.monetary_index import MonetaryIndex  # noqa: F401
from app.models.opportunity_alert import (  # noqa: F401  (registers the tables)
    CollectionRun,
    OpportunityAlertConfig,
    OpportunityNotification,
)
from app.models.transaction import Transaction  # noqa: F401  (registers the table)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
