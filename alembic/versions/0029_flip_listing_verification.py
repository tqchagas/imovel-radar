"""Track direct listing-page checks for the flip garimpo.

Revision ID: 0029_flip_listing_verification
Revises: 0028_flip_orcamento_aferivel
"""

from alembic import op
import sqlalchemy as sa

revision = "0029_flip_listing_verification"
down_revision = "0028_flip_orcamento_aferivel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_comparables",
        sa.Column(
            "page_verification_status",
            sa.String(length=20),
            server_default="unverified",
            nullable=False,
        ),
    )
    op.add_column(
        "market_comparables",
        sa.Column("page_verification_checked_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "market_comparables",
        sa.Column("page_verification_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_market_comparables_page_verification_status",
        "market_comparables",
        ["page_verification_status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_comparables_page_verification_status",
        table_name="market_comparables",
    )
    op.drop_column("market_comparables", "page_verification_error")
    op.drop_column("market_comparables", "page_verification_checked_at")
    op.drop_column("market_comparables", "page_verification_status")
