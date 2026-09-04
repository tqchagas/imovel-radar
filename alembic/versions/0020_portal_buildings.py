"""O prédio como o portal o publica, com o número da rua.

O cadastro da prefeitura sabe o que existe no endereço; faltava saber em que
endereço o anúncio está. O QuintoAndar publica isso num diretório de
condomínios indexado no sitemap e liberado pelo robots.txt — 19.117 páginas em
Belo Horizonte, uma por prédio, cada uma com rua, número, CEP, coordenada,
faixa de área das unidades e as instalações do edifício.

Medido em 59 páginas sorteadas: 59 trazem o número, 49 (83%) casam com o
cadastro por rua+número, e o ponto publicado fica a 8 m (mediana) do lote do
cadastro e a 1 m do anúncio do próprio portal.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_buildings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(50), nullable=False),
        sa.Column("slug", sa.String(300), nullable=True),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("street", sa.String(300), nullable=True),
        sa.Column("street_number", sa.String(30), nullable=True),
        sa.Column("street_key", sa.String(300), nullable=True),
        sa.Column("number_key", sa.String(30), nullable=True),
        sa.Column("postal_code", sa.String(9), nullable=True),
        sa.Column("neighborhood", sa.String(150), nullable=True),
        sa.Column("lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("lon", sa.Numeric(9, 6), nullable=True),
        sa.Column("min_area", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_area", sa.Numeric(10, 2), nullable=True),
        sa.Column("min_bedrooms", sa.Integer(), nullable=True),
        sa.Column("max_bedrooms", sa.Integer(), nullable=True),
        sa.Column("installations", sa.JSON(), nullable=True),
        sa.Column("doorman", sa.String(50), nullable=True),
        sa.Column("source_lastmod", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source", "external_id", name="uq_portal_buildings_source_external"
        ),
    )
    op.create_index("ix_portal_buildings_source", "portal_buildings", ["source"])
    op.create_index("ix_portal_buildings_city", "portal_buildings", ["city"])
    op.create_index("ix_portal_buildings_street_key", "portal_buildings", ["street_key"])
    op.create_index("ix_portal_buildings_neighborhood", "portal_buildings", ["neighborhood"])
    op.create_index("ix_portal_buildings_lat", "portal_buildings", ["lat"])
    op.create_index("ix_portal_buildings_lon", "portal_buildings", ["lon"])


def downgrade() -> None:
    op.drop_table("portal_buildings")
