"""create transactions table

Revision ID: 0001
Revises:
Create Date: 2026-07-13

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_address", sa.String(length=500), nullable=False),
        sa.Column("street_line", sa.String(length=300), nullable=False),
        sa.Column("postal_code", sa.String(length=9), nullable=True),
        sa.Column("neighborhood", sa.String(length=150), nullable=False),
        sa.Column("construction_year", sa.Integer(), nullable=True),
        sa.Column("land_area", sa.Numeric(14, 2), nullable=True),
        sa.Column("built_area_acquired", sa.Numeric(14, 2), nullable=True),
        sa.Column("acquired_area_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("finish_standard", sa.String(length=10), nullable=True),
        sa.Column("acquired_fraction", sa.Numeric(10, 6), nullable=True),
        sa.Column("construction_type", sa.String(length=10), nullable=True),
        sa.Column("occupation_type", sa.String(length=50), nullable=True),
        sa.Column("declared_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("calc_base_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("zoning", sa.String(length=20), nullable=True),
        sa.Column("settlement_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("source_row_hash", name="uq_transactions_source_row_hash"),
    )
    op.create_index("ix_transactions_city", "transactions", ["city"])
    op.create_index("ix_transactions_neighborhood", "transactions", ["neighborhood"])
    op.create_index(
        "ix_transactions_settlement_date", "transactions", ["settlement_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_settlement_date", table_name="transactions")
    op.drop_index("ix_transactions_neighborhood", table_name="transactions")
    op.drop_index("ix_transactions_city", table_name="transactions")
    op.drop_table("transactions")
