"""Rank opportunities on a single 0-100 score.

Discount and confidence are two axes that cannot be compared against each
other: 70% off a whole-neighborhood sample is weaker evidence than 32% off an
exact-address one. The score collapses them into one ordering, and the sample
dispersion it is derived from is stored alongside so the number can be
explained after the fact.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_comparables", sa.Column("nota", sa.Integer(), nullable=True))
    op.add_column(
        "market_comparables",
        sa.Column("dispersao_relativa", sa.Numeric(7, 4), nullable=True),
    )
    op.add_column(
        "market_comparables",
        sa.Column("fator_calibracao", sa.Numeric(7, 4), nullable=True),
    )
    op.add_column(
        "market_comparables",
        sa.Column("unidade_fingerprint", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_market_comparables_nota", "market_comparables", ["nota"]
    )
    op.create_index(
        "ix_market_comparables_unidade_fingerprint",
        "market_comparables",
        ["unidade_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_comparables_unidade_fingerprint", "market_comparables")
    op.drop_index("ix_market_comparables_nota", "market_comparables")
    op.drop_column("market_comparables", "unidade_fingerprint")
    op.drop_column("market_comparables", "fator_calibracao")
    op.drop_column("market_comparables", "dispersao_relativa")
    op.drop_column("market_comparables", "nota")
