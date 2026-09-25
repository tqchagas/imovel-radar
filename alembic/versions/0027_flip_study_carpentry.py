"""Escolha de marcenaria nos estudos de flip.

Os orçamentos anteriores sempre incluíam os gabinetes de cozinha e banheiros;
por isso a coluna nasce verdadeira também para os estudos já salvos.

Revision ID: 0027
Revises: 0026
"""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "flip_studies",
        sa.Column(
            "incluir_marcenaria", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )


def downgrade() -> None:
    op.drop_column("flip_studies", "incluir_marcenaria")
