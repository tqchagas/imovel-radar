"""Gate alerts on the 0-100 score instead of the confidence tier.

The tier was a proxy for how trustworthy the reference was; the score measures
that directly, from the sample's own dispersion and size. A neighborhood-wide
sample of 730 sales spread over 17% is better evidence than a street sample of
16 spread over 31%, and only the score can say so.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode: SQLite cannot ALTER a constraint into an existing table.
    with op.batch_alter_table("opportunity_alert_configs", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("nota_minima", sa.Integer(), nullable=False, server_default="80")
        )
        batch_op.create_check_constraint(
            "ck_opportunity_alert_configs_nota_minima",
            "nota_minima BETWEEN 0 AND 100",
        )


def downgrade() -> None:
    with op.batch_alter_table("opportunity_alert_configs", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "ck_opportunity_alert_configs_nota_minima", type_="check"
        )
        batch_op.drop_column("nota_minima")
