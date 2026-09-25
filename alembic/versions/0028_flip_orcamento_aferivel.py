"""Escopo e quantitativos do orçamento aferível.

Estudos anteriores permanecem no motor legado.

Revision ID: 0028
Revises: 0027
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("flip_studies") as batch:
        batch.add_column(sa.Column("escopo_obra", sa.String(20), nullable=False, server_default="legado"))
        batch.add_column(sa.Column("quantidades_json", sa.Text(), nullable=False, server_default="{}"))
        batch.create_check_constraint("ck_flip_studies_escopo", "escopo_obra IN ('legado', 'retoques', 'revenda', 'retrofit')")


def downgrade() -> None:
    with op.batch_alter_table("flip_studies") as batch:
        batch.drop_constraint("ck_flip_studies_escopo", type_="check")
        batch.drop_column("quantidades_json")
        batch.drop_column("escopo_obra")
