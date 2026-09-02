"""Neighbourhood context from QuintoAndar's similar-houses endpoint.

The price suggestion only answers for QuintoAndar listings - it resolves the
unit from the listing id and 404s on anything else. This endpoint asks by
coordinate instead, so it covers Loft and VivaReal too, and it returns what an
asking price alone cannot say: the R$/m2 of listings still on the market, the
R$/m2 of ones already off it (closer to transactions than to asking), and how
many days a deal takes in that region.

It is neighbourhood context, not a valuation of the unit - a flat can sit below
its area's average because it is worse - so it informs the screen and stays out
of the score.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_comparables",
        sa.Column("similares_m2_anunciado", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "market_comparables",
        sa.Column("similares_m2_negociado", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "market_comparables",
        sa.Column("similares_dias_ate_negocio", sa.Integer(), nullable=True),
    )
    op.add_column(
        "market_comparables", sa.Column("similares_updated_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("market_comparables", "similares_updated_at")
    op.drop_column("market_comparables", "similares_dias_ate_negocio")
    op.drop_column("market_comparables", "similares_m2_negociado")
    op.drop_column("market_comparables", "similares_m2_anunciado")
