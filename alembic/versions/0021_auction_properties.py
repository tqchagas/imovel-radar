"""Imóvel de leilão digitado à mão, e o histórico das avaliações.

O produto parte de anúncio coletado, e imóvel de leilão não está anunciado. O
que existe é o edital: endereço, área de matrícula e uma avaliação judicial que
costuma estar velha. Falta saber por quanto ele se revende hoje.

A Calculadora QPreço do QuintoAndar responde isso para endereço arbitrário, sem
anúncio e sem sessão, e na mesma consulta devolve os comparáveis que ela reporta
como vendidos. São duas leituras independentes, e é a divergência entre elas que
diz se dá para confiar.

O portal publica três preços, e o destaque da tela dele não é o do meio: o que
ele chama de "Venda por / Ideal" é o menor, e "na média dos similares" é o maior.
São os mesmos valores que `dealObjectiveRanges` devolve como FASTER e SLOWER —
conferido idêntico em três imóveis. Guardá-los como "faixa" esconderia o que
significam, então cada um tem a sua coluna.

O histórico é tabela à parte porque o dono reconsulta antes do leilão, e o valor
está em ver o número se mover.

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auction_properties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("apelido", sa.String(150), nullable=True),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("address_number", sa.String(30), nullable=True),
        sa.Column("neighborhood", sa.String(150), nullable=True),
        sa.Column("city", sa.String(150), nullable=False),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("coordenada_fonte", sa.String(50), nullable=True),
        sa.Column("house_type", sa.String(20), nullable=False, server_default="APARTMENT"),
        sa.Column("total_area", sa.Numeric(10, 2), nullable=False),
        sa.Column("bedroom_count", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("bathroom_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("suites_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parking_slots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("condominium_per_month", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("iptu_per_year", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("data_leilao", sa.Date(), nullable=True),
        sa.Column("lance_minimo", sa.Numeric(14, 2), nullable=True),
        sa.Column("edital_url", sa.String(1000), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_auction_properties_city", "auction_properties", ["city"])
    op.create_index("ix_auction_properties_data_leilao", "auction_properties", ["data_leilao"])

    op.create_table(
        "auction_appraisals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "auction_property_id",
            sa.Integer(),
            sa.ForeignKey("auction_properties.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("consultado_em", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("preco_qpreco", sa.Numeric(14, 2), nullable=True),
        sa.Column("preco_rapido", sa.Numeric(14, 2), nullable=True),
        sa.Column("preco_devagar", sa.Numeric(14, 2), nullable=True),
        sa.Column("limite_inferior", sa.Numeric(14, 2), nullable=True),
        sa.Column("limite_superior", sa.Numeric(14, 2), nullable=True),
        sa.Column("certeza", sa.String(20), nullable=True),
        sa.Column("preco_vendidos", sa.Numeric(14, 2), nullable=True),
        sa.Column("comparaveis_usados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("divergencia_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("atipico", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preco_itbi", sa.Numeric(14, 2), nullable=True),
        sa.Column("itbi_tier", sa.String(30), nullable=True),
        sa.Column("itbi_amostra", sa.Integer(), nullable=True),
        sa.Column("comparaveis_json", sa.JSON(), nullable=True),
        sa.Column("erro", sa.String(300), nullable=True),
    )
    op.create_index(
        "ix_auction_appraisals_property", "auction_appraisals", ["auction_property_id"]
    )


def downgrade() -> None:
    op.drop_table("auction_appraisals")
    op.drop_table("auction_properties")
