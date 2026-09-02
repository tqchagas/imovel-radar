"""Record how each listing moves, so alerts can be scored after the fact.

The comparables table only holds the latest state of a listing. Whether the
model was right is only visible in the movement: a price that falls and then a
listing that stops appearing is the closest thing to a sale we can observe.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_price_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("listing_id", sa.String(100), nullable=False),
        sa.Column("event", sa.String(20), nullable=False),
        sa.Column("preco_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("preco_anterior", sa.Numeric(14, 2), nullable=True),
        sa.Column("nota", sa.Integer(), nullable=True),
        sa.Column("desconto_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event IN ('listed', 'price_changed', 'delisted', 'relisted')",
            name="ck_listing_price_events_event",
        ),
    )
    op.create_index(
        "ix_listing_price_events_listing",
        "listing_price_events",
        ["source", "listing_id", "observed_at"],
    )
    op.create_index("ix_listing_price_events_event", "listing_price_events", ["event"])
    op.create_index(
        "ix_listing_price_events_observed_at", "listing_price_events", ["observed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_listing_price_events_observed_at", "listing_price_events")
    op.drop_index("ix_listing_price_events_event", "listing_price_events")
    op.drop_index("ix_listing_price_events_listing", "listing_price_events")
    op.drop_table("listing_price_events")
