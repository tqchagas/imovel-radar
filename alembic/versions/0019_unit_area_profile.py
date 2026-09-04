"""O formato do prédio, e não só o tamanho da unidade típica.

O cadastro já guardava a mediana das áreas e o quanto elas discordam entre si.
Falta o formato: em 24% dos prédios a dispersão passa de 0,30, e ali a mediana
está descrevendo um apartamento que ninguém tem — ela compara a cobertura com o
quarto e sala.

Onze decis resolvem isso sem guardar unidade a unidade. Com eles, o anúncio
encontra a sua unidade pelo posto que ocupa entre os anúncios do mesmo prédio,
e o posto compara área anunciada com área anunciada — o que faz a diferença
entre área construída e área útil se cancelar em vez de virar erro.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registry_addresses", sa.Column("unit_area_profile", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("registry_addresses", "unit_area_profile")
