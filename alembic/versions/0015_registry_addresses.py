"""Cadastro imobiliário municipal: endereço com a coordenada do lote.

A escada de referência só alcança o tier de endereço exato quando o anúncio traz
o número da rua, e só o VivaReal traz - a Loft e o QuintoAndar publicam a rua e
a coordenada, nunca o número. Isso deixava 84% do inventário preso no tier de
rua ou pior, onde o erro medido da referência é 14-25% contra os 5-13% do
endereço.

A prefeitura publica o cadastro tributário georreferenciado, e ele fecha essa
lacuna: cobre 99,6% dos endereços de ITBI de apartamento, e a coordenada do
lote cai a 12 m (mediana) do ponto que o portal publica para o mesmo endereço.
Casando pela rua do anúncio mais a coordenada, num raio de 50 m, o número certo
sai em 93% dos casos - medido contra os 1.530 anúncios do VivaReal que publicam
número e coordenada exata.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "registry_addresses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("street", sa.String(300), nullable=False),
        sa.Column("street_number", sa.String(30), nullable=False),
        sa.Column("street_key", sa.String(300), nullable=False),
        sa.Column("number_key", sa.String(30), nullable=False),
        sa.Column("postal_code", sa.String(9), nullable=True),
        sa.Column("neighborhood", sa.String(150), nullable=True),
        sa.Column("construction_type", sa.String(10), nullable=False),
        sa.Column("occupation_type", sa.String(50), nullable=True),
        sa.Column("finish_standard", sa.String(10), nullable=True),
        sa.Column("units_count", sa.Integer(), nullable=True),
        sa.Column("median_unit_area", sa.Numeric(10, 2), nullable=True),
        sa.Column("lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("lon", sa.Numeric(9, 6), nullable=True),
        sa.Column("source_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "city", "street_key", "number_key", "construction_type",
            name="uq_registry_addresses_endereco",
        ),
    )
    op.create_index("ix_registry_addresses_city", "registry_addresses", ["city"])
    op.create_index("ix_registry_addresses_street_key", "registry_addresses", ["street_key"])
    op.create_index("ix_registry_addresses_construction_type", "registry_addresses", ["construction_type"])
    # A busca por coordenada varre uma célula de grade; o índice composto é o
    # que evita o seq scan em 31 mil lotes a cada anúncio.
    op.create_index("ix_registry_addresses_coord", "registry_addresses", ["lat", "lon"])


def downgrade() -> None:
    op.drop_index("ix_registry_addresses_coord", table_name="registry_addresses")
    op.drop_index("ix_registry_addresses_construction_type", table_name="registry_addresses")
    op.drop_index("ix_registry_addresses_street_key", table_name="registry_addresses")
    op.drop_index("ix_registry_addresses_city", table_name="registry_addresses")
    op.drop_table("registry_addresses")
