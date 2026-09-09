"""A série do IPCA, mês a mês.

A base vai de 2008 a 2026 e todo valor é impresso em reais do dia da quitação.
Sem uma série de índice gravada não há como dizer que R$ 300.000 de 2008 valem
2,7x R$ 300.000 de 2025.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monetary_index",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series", sa.String(length=20), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("variacao_pct", sa.Numeric(8, 4), nullable=False),
        sa.UniqueConstraint("series", "competencia", name="uq_monetary_index_serie_mes"),
    )
    op.create_index("ix_monetary_index_series", "monetary_index", ["series"])


def downgrade() -> None:
    op.drop_index("ix_monetary_index_series", table_name="monetary_index")
    op.drop_table("monetary_index")
