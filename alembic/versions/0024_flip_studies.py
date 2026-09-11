"""Estudos de flip salvos.

O simulador calcula em memória, mas a decisão de comprar leva semanas e passa
por vários imóveis ao mesmo tempo — sem tabela, cada estudo morre no refresh.

As premissas de custo vão junto, como snapshot: elas moram num JSON versionado
no repositório, e reajustar o preço do granito não pode mexer no lucro de um
estudo fechado há seis meses.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flip_studies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("apelido", sa.String(150), nullable=True),
        sa.Column("endereco", sa.String(300), nullable=False),
        sa.Column("bairro", sa.String(150), nullable=True),
        sa.Column("cidade", sa.String(150), nullable=False, server_default="belo_horizonte"),
        sa.Column("area_util_m2", sa.Numeric(10, 2), nullable=False),
        sa.Column("area_seca_m2", sa.Numeric(10, 2), nullable=False),
        sa.Column("quartos", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("banheiros", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cozinhas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("portas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preco_compra", sa.Numeric(14, 2), nullable=False),
        sa.Column("arv_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("meses_carrego", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("eletrica_completa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "hidraulica_completa_banheiro", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "hidraulica_completa_cozinha", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="em_analise"),
        sa.Column("origem", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("origem_id", sa.Integer(), nullable=True),
        sa.Column("premissas_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('oportunidade', 'em_analise', 'descartado')",
            name="ck_flip_studies_status",
        ),
        sa.CheckConstraint(
            "origem IN ('manual', 'oportunidade', 'leilao')", name="ck_flip_studies_origem"
        ),
        sa.CheckConstraint("area_seca_m2 > 0", name="ck_flip_studies_area_seca"),
        sa.CheckConstraint("preco_compra > 0", name="ck_flip_studies_preco"),
        sa.CheckConstraint("meses_carrego >= 0", name="ck_flip_studies_meses"),
    )
    op.create_index("ix_flip_studies_bairro", "flip_studies", ["bairro"])
    op.create_index("ix_flip_studies_status", "flip_studies", ["status"])


def downgrade() -> None:
    op.drop_index("ix_flip_studies_status", table_name="flip_studies")
    op.drop_index("ix_flip_studies_bairro", table_name="flip_studies")
    op.drop_table("flip_studies")
