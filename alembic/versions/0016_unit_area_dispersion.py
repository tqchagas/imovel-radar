"""Dispersão das áreas das unidades de um endereço do cadastro.

A janela de área compara o anúncio contra vendas de ITBI cuja área construída
caia a ±30% da área anunciada convertida por um fator único da cidade, 1,6.
Medido prédio a prédio contra o cadastro, esse fator vai de 0,80 (p10) a 2,21
(p90) - varia quase três vezes -, então a janela fica centrada no lugar errado
para a maioria dos endereços e recusa vendas do próprio prédio: dos 5.379
anúncios da Loft cujo prédio o ITBI enxerga, só 1.966 sobrevivem a ela.

No tier de endereço a janela quase não tem o que discriminar: a mediana da
dispersão das áreas dentro de um prédio é 0,09, e 76% dos prédios ficam abaixo
de 0,30 - mais estreitos do que a própria tolerância da janela. Guardar essa
dispersão permite dispensá-la onde ela só faz perder amostra.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registry_addresses",
        sa.Column("unit_area_dispersion", sa.Numeric(7, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("registry_addresses", "unit_area_dispersion")
