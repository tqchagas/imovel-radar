"""Store the numbers each alert was sent with, so resends can compare them.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunity_notifications",
        sa.Column("payload_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("opportunity_notifications", "payload_json")
