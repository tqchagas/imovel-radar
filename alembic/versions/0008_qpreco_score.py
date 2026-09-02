"""Score each listing against QuintoAndar's own estimate as well as the ITBI.

The ITBI reference and the portal's "qpreço" are independent readings of the
same unit, and a discount only means something when both agree. The final
`nota` is the lower of the two, so these columns keep each half visible: which
reference dragged the score down is otherwise impossible to tell after the run.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_comparables", sa.Column("nota_itbi", sa.Integer(), nullable=True))
    op.add_column("market_comparables", sa.Column("nota_qpreco", sa.Integer(), nullable=True))
    op.add_column(
        "market_comparables",
        sa.Column("qpreco_desconto_pct", sa.Numeric(7, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("market_comparables", "qpreco_desconto_pct")
    op.drop_column("market_comparables", "nota_qpreco")
    op.drop_column("market_comparables", "nota_itbi")
