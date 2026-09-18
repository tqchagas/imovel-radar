"""Marca a quitação que é contrato da planta registrado tarde.

O ITBI publica a data de quitação, não a do negócio. A primeira quitação de uma
unidade que aparece anos depois do lançamento, pelo R$/m² do lançamento, é
contrato antigo: fica na história do imóvel e sai das estatísticas. A regra
está em `app.domain.late_registration`; o backfill roda o mesmo serviço que a
ingestão chama.

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from app.services.late_registration import mark_late_registrations

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

    conn = op.get_bind()
    session = Session(bind=conn)
    for (city,) in conn.execute(sa.text("SELECT DISTINCT city FROM transactions")).all():
        mark_late_registrations(session, city)


def downgrade() -> None:
    op.drop_column("transactions", "late_registration")
