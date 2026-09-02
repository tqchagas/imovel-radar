"""Widen `referencia_primaria`: "qpreco_vizinho" does not fit in ten characters.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode: o SQLite nao sabe ALTER COLUMN TYPE, e a suite roda as
    # migrations nele.
    with op.batch_alter_table("market_comparables") as batch_op:
        batch_op.alter_column(
            "referencia_primaria",
            type_=sa.String(20), existing_type=sa.String(10), existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("market_comparables") as batch_op:
        batch_op.alter_column(
            "referencia_primaria",
            type_=sa.String(10), existing_type=sa.String(20), existing_nullable=True,
        )
