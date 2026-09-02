"""Record where a listing's area came from.

The Loft search leaves `area` empty on 31% of its listings, and the metre count
is usually in the free-text description. Read from there it disagrees with the
published number about 13% of the time, almost always by naming a part ("73 m²
interna + 87 m² terraço") where the portal publishes the sum - and the error
skews low, which inflates the asking R$/m². Those listings get an estimate and
a screen row, but never an alert and never a vote in the calibration factor.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_comparables", sa.Column("area_origem", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("market_comparables", "area_origem")
