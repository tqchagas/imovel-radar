"""Desfecho de um anúncio: o que ele de fato virou no ITBI.

Nada no projeto sabe hoje se um alerta prestou. A escada de referência é
validada contra o próprio ITBI, e a calibração contra o preço pedido de
anúncios escondidos — as duas medem se a estimativa acerta um número que já
existe, não se o imóvel era mesmo uma oportunidade.

A resposta gabaritada é o encontro das duas fontes: um anúncio que sai do ar e
reaparece como quitação de ITBI no mesmo endereço, meses depois, entrega o
preço pelo qual o negócio de fato fechou. Contra ele dá para perguntar o que
nenhuma outra medida responde — os anúncios que marcamos com nota alta fecharam
mais barato que os outros? — e medir o desconto de negociação por unidade em
vez de por um fator único da cidade.

Isto começa a valer com o calendário, não com o código: `listing_price_events`
tem dias de vida e o ITBI de Belo Horizonte atrasa dois meses. A primeira
coorte mensurável cai por volta de janeiro de 2027. Por isso a gravação começa
agora.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "listing_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("listing_id", sa.String(100), nullable=False),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("delisted_at", sa.DateTime(), nullable=False),
        # O que o modelo dizia no momento em que o anúncio saiu do ar.
        sa.Column("preco_anunciado", sa.Numeric(14, 2), nullable=True),
        sa.Column("preco_estimado", sa.Numeric(14, 2), nullable=True),
        sa.Column("desconto_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("nota", sa.Integer(), nullable=True),
        sa.Column("tipo_referencia", sa.String(30), nullable=True),
        # A quitação que o encontrou.
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("valor_realizado", sa.Numeric(14, 2), nullable=True),
        # Como o par foi feito: "endereco" quando o número era publicado,
        # "coordenada" quando veio do cadastro. O segundo herda os 6,5% de erro
        # da resolução e não pode ser lido como se fosse o primeiro.
        sa.Column("match_method", sa.String(30), nullable=True),
        sa.Column("candidatos", sa.Integer(), nullable=True),
        sa.Column("matched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "listing_id", "delisted_at", name="uq_listing_outcomes_saida"),
    )
    op.create_index("ix_listing_outcomes_city", "listing_outcomes", ["city"])
    op.create_index("ix_listing_outcomes_settlement", "listing_outcomes", ["settlement_date"])
    # A varredura procura os desfechos ainda em aberto a cada rodada.
    op.create_index("ix_listing_outcomes_pendentes", "listing_outcomes", ["matched_at"])


def downgrade() -> None:
    op.drop_index("ix_listing_outcomes_pendentes", table_name="listing_outcomes")
    op.drop_index("ix_listing_outcomes_settlement", table_name="listing_outcomes")
    op.drop_index("ix_listing_outcomes_city", table_name="listing_outcomes")
    op.drop_table("listing_outcomes")
