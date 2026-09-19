"""Confiança da marca de registro tardio.

"alta" quando o preço da quitação fica abaixo tanto do lançamento quanto das
revendas do prédio naquele ano; "media" quando só uma das duas referências
existe. As duas saem das estatísticas — medido em `scripts/validar_tardios.py`,
tirar só as de confiança alta erra mais —; a confiança serve para a tela dizer
o quanto a marca é segura.

Como a 0025, só cria a coluna: `marcar-tardios` preenche.

Revision ID: 0026
Revises: 0025
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("late_registration_confidence", sa.String(length=5), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "late_registration_confidence")
