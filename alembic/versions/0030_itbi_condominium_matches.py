"""Persist exact-address ITBI to QuintoAndar building matches.

Revision ID: 0030_itbi_condominium_matches
Revises: 0029_flip_listing_verification
"""

from alembic import op
import sqlalchemy as sa

revision = "0030_itbi_condominium_matches"
down_revision = "0029_flip_listing_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "portal_building_id",
            sa.Integer(),
            sa.ForeignKey("portal_buildings.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("condo_match_status", sa.String(20), server_default="pending", nullable=False),
    )
    op.add_column("transactions", sa.Column("condo_match_score", sa.Integer(), nullable=True))
    op.add_column("transactions", sa.Column("condo_match_evidence", sa.JSON(), nullable=True))
    op.add_column("transactions", sa.Column("condo_match_candidates", sa.JSON(), nullable=True))
    op.add_column("transactions", sa.Column("condo_match_updated_at", sa.DateTime(), nullable=True))
    op.create_index("ix_transactions_portal_building_id", "transactions", ["portal_building_id"])
    op.create_index("ix_transactions_condo_match_status", "transactions", ["condo_match_status"])


def downgrade() -> None:
    op.drop_index("ix_transactions_condo_match_status", table_name="transactions")
    op.drop_index("ix_transactions_portal_building_id", table_name="transactions")
    op.drop_column("transactions", "condo_match_updated_at")
    op.drop_column("transactions", "condo_match_candidates")
    op.drop_column("transactions", "condo_match_evidence")
    op.drop_column("transactions", "condo_match_score")
    op.drop_column("transactions", "condo_match_status")
    op.drop_column("transactions", "portal_building_id")
