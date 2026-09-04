"""O prédio que o QuintoAndar já publicava e o coletor não pedia.

O gateway de busca devolve só os campos que a requisição lista, e a lista não
pedia `condoId`. Sondado ao vivo em 1.000 anúncios de Belo Horizonte, ele vem
em 998 — e agrupa sem erro: a coordenada dentro de um mesmo id tem
espalhamento mediano de 0 m e máximo de 13 m.

Isso importa porque a limitação mais cara da escada de referência é que Loft e
QuintoAndar publicam a rua e não publicam o número. Sem número o anúncio nunca
alcança o tier de endereço exato, onde o erro medido é 5-13% contra 14-25% na
rua e no bairro. O `condoId` é o portal dizendo em que prédio o anúncio está,
sem custo de requisição e sem adivinhação por proximidade de lote.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_comparables", sa.Column("condo_id", sa.String(50), nullable=True))
    op.add_column("market_comparables", sa.Column("condo_name", sa.String(300), nullable=True))
    op.create_index("ix_market_comparables_condo_id", "market_comparables", ["condo_id"])


def downgrade() -> None:
    op.drop_index("ix_market_comparables_condo_id", table_name="market_comparables")
    op.drop_column("market_comparables", "condo_name")
    op.drop_column("market_comparables", "condo_id")
