"""Keep the portal's publication date.

Half of Loft's stock has been listed for more than a year - median 419 days
across 300 Belo Horizonte listings, 165 of them past twelve months. A discount
on a listing the market has been refusing for fourteen months is not the same
finding as a discount on one published last week, and `first_seen_at` cannot
tell them apart: it only knows when *we* first looked.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_comparables", sa.Column("anunciado_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("market_comparables", "anunciado_em")
