"""expand market comparables and add opportunity alert tables

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the first snapshot for each listing before adding the legacy-table constraint.
    op.execute(
        sa.text(
            "DELETE FROM market_comparables "
            "WHERE id NOT IN ("
            "SELECT MIN(id) FROM market_comparables GROUP BY source, listing_id"
            ")"
        )
    )
    with op.batch_alter_table("market_comparables", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("url", sa.String(1000), nullable=True))
        batch_op.add_column(sa.Column("coordinate_source", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("bairro", sa.String(150), nullable=True))
        batch_op.add_column(sa.Column("rua", sa.String(300), nullable=True))
        batch_op.add_column(sa.Column("numero", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("cidade_normalizada", sa.String(150), nullable=True))
        batch_op.add_column(sa.Column("bairro_normalizado", sa.String(150), nullable=True))
        batch_op.add_column(sa.Column("rua_normalizada", sa.String(300), nullable=True))
        batch_op.add_column(sa.Column("numero_normalizado", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("collection_scope_key", sa.String(500), nullable=True))
        batch_op.add_column(sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch_op.add_column(sa.Column("activation_event_id", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("preco_estimado", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("desconto_pct", sa.Numeric(7, 4), nullable=True))
        batch_op.add_column(sa.Column("desconto_reais", sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("tipo_referencia", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("amostra_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("referencia_data_inicio", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("referencia_data_fim", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("confianca", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("oportunidade_motivo", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("oportunidade_fingerprint", sa.String(64), nullable=True))
        batch_op.create_unique_constraint(
            "uq_market_comparables_source_listing", ["source", "listing_id"]
        )

    op.create_index("ix_market_comparables_cidade_normalizada", "market_comparables", ["cidade_normalizada"])
    op.create_index("ix_market_comparables_bairro_normalizado", "market_comparables", ["bairro_normalizado"])
    op.create_index("ix_market_comparables_rua_normalizada", "market_comparables", ["rua_normalizada"])
    op.create_index("ix_market_comparables_ativo", "market_comparables", ["ativo"])
    op.create_index("ix_market_comparables_collection_scope_key", "market_comparables", ["collection_scope_key"])

    op.create_table(
        "opportunity_alert_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cidade", sa.String(150), nullable=False),
        sa.Column("bairros_json", sa.Text(), nullable=False),
        sa.Column("desconto_minimo_pct", sa.Numeric(7, 4), nullable=False),
        sa.Column("confianca_minima", sa.String(20), nullable=False),
        sa.Column("destinatarios_json", sa.Text(), nullable=False),
        sa.Column("periodicidade_minutos", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint("confianca_minima IN ('baixa', 'media', 'alta')", name="ck_opportunity_alert_configs_confidence"),
    )
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("cidade", sa.String(150), nullable=False),
        sa.Column("bairros_json", sa.Text(), nullable=False),
        sa.Column("filtros_json", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("pages_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('running', 'success', 'partial', 'failed')", name="ck_collection_runs_status"),
    )
    op.create_index("ix_collection_runs_source", "collection_runs", ["source"])
    op.create_index("ix_collection_runs_scope_key", "collection_runs", ["scope_key"])
    op.create_table(
        "opportunity_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("market_comparable_id", sa.Integer(), sa.ForeignKey("market_comparables.id"), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("activation_event_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("destinatarios_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name="ck_opportunity_notifications_status"),
        sa.UniqueConstraint(
            "market_comparable_id",
            "rule_version",
            "activation_event_id",
            "fingerprint",
            name="uq_opportunity_notifications_dedup",
        ),
    )


def downgrade() -> None:
    op.drop_table("opportunity_notifications")
    op.drop_index("ix_collection_runs_scope_key", table_name="collection_runs")
    op.drop_index("ix_collection_runs_source", table_name="collection_runs")
    op.drop_table("collection_runs")
    op.drop_table("opportunity_alert_configs")
    for index in (
        "ix_market_comparables_collection_scope_key",
        "ix_market_comparables_ativo",
        "ix_market_comparables_rua_normalizada",
        "ix_market_comparables_bairro_normalizado",
        "ix_market_comparables_cidade_normalizada",
    ):
        op.drop_index(index, table_name="market_comparables")
    with op.batch_alter_table("market_comparables", recreate="always") as batch_op:
        batch_op.drop_constraint("uq_market_comparables_source_listing", type_="unique")
        for column in (
            "oportunidade_fingerprint", "oportunidade_motivo", "confianca",
            "referencia_data_fim", "referencia_data_inicio", "amostra_count",
            "tipo_referencia", "desconto_reais", "desconto_pct", "preco_estimado",
            "activation_event_id", "last_seen_at", "first_seen_at", "collection_scope_key",
            "ativo", "numero_normalizado", "rua_normalizada", "bairro_normalizado",
            "cidade_normalizada", "numero", "rua", "bairro", "coordinate_source", "url",
        ):
            batch_op.drop_column(column)
