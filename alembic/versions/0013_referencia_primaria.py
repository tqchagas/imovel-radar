"""Let the sharpest available reference answer "what is it worth".

Cross-validation on 3.958 held-out listings: predicting an asking price from
the ITBI ladder errs 22,2% at the median, and misses by more than 40% in a
quarter of cases - the same order of magnitude as the discounts the feed calls
opportunities. QuintoAndar's own estimate looks at the unit and publishes a
band around 5%.

So where a qpreço exists it becomes the expected price, and the ITBI reading
becomes the check kept alongside it. The alert floor follows: it is now a
multiple of the answering reference's measured error - 30% against a street
tier, 7,5% against a narrow qpreço band - instead of one fixed 30% that meant
different things depending on who answered.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_comparables", sa.Column("referencia_primaria", sa.String(10), nullable=True)
    )
    op.add_column(
        "market_comparables", sa.Column("preco_estimado_itbi", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column(
        "market_comparables", sa.Column("desconto_itbi_pct", sa.Numeric(7, 4), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("market_comparables", "desconto_itbi_pct")
    op.drop_column("market_comparables", "preco_estimado_itbi")
    op.drop_column("market_comparables", "referencia_primaria")
