"""create market_comparables table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_comparables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("listing_id", sa.String(length=100), nullable=False),
        sa.Column("cidade", sa.String(length=150), nullable=True),
        sa.Column("tipo_imovel", sa.String(length=50), nullable=True),
        sa.Column("lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("lon", sa.Numeric(9, 6), nullable=True),
        sa.Column("bathrooms", sa.Integer(), nullable=True),
        sa.Column("bedrooms", sa.Integer(), nullable=True),
        sa.Column("parking_spaces", sa.Integer(), nullable=True),
        sa.Column("suites", sa.Integer(), nullable=True),
        sa.Column("area_util_m2", sa.Numeric(10, 2), nullable=True),
        sa.Column("preco_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("condominium_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("iptu_value", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_suggestion_json", sa.Text(), nullable=True),
        sa.Column("price_suggestion_lower_bound", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_suggestion_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_suggestion_upper_bound", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_suggestion_updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_market_comparables_source", "market_comparables", ["source"])
    op.create_index(
        "ix_market_comparables_listing_id", "market_comparables", ["listing_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_market_comparables_listing_id", table_name="market_comparables")
    op.drop_index("ix_market_comparables_source", table_name="market_comparables")
    op.drop_table("market_comparables")
