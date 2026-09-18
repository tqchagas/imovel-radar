"""Marca a quitação que é contrato da planta registrado tarde.

O ITBI publica a data de quitação, não a do negócio. A primeira quitação de uma
unidade que aparece anos depois do lançamento, pelo R$/m² do lançamento, é
contrato antigo: fica na história do imóvel e sai das estatísticas.

A migração só cria a coluna. Quem preenche é o comando `marcar-tardios`, que o
scheduler roda a cada ciclo (e `make tardios` roda à mão): a regra, em
`app.domain.late_registration`, vai mudar com o tempo, e uma migração que a
importasse rodaria a versão nova numa base criada do zero.

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "late_registration", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("transactions", "late_registration")
