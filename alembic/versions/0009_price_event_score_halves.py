"""Keep both halves of the score on every listing event.

The final score is the lower of the ITBI reading and the QuintoAndar one, so it
cannot say which reference decided. An outcome study has to compare exactly
those cohorts - flagged, vetoed by the qpreço, never a candidate - and the state
is gone by the time the study runs. Recorded now or never.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listing_price_events", sa.Column("nota_itbi", sa.Integer(), nullable=True))
    op.add_column("listing_price_events", sa.Column("nota_qpreco", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("listing_price_events", "nota_qpreco")
    op.drop_column("listing_price_events", "nota_itbi")
