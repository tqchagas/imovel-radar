"""A rua numa forma que a busca consegue comparar.

O filtro de rua da `/busca` era `ILIKE` sobre o texto cru que o cartório
publica. O LIKE do banco só ignora caixa em ASCII, então "São João" não
encontrava "RUA SAO JOAO" e "Avenida" não encontrava "AVE" — quem digitava o
endereço como se escreve recebia zero quitação e concluía que a base não tinha
o imóvel.

A coluna guarda a mesma rua sem acento, sem pontuação e com o tipo do
logradouro por extenso (`street_search_text`). O backfill percorre ruas
distintas, e não linhas: são poucos milhares de logradouros para centenas de
milhares de quitações.

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op

from app.domain.slugs import street_search_text

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

INSERT_CHUNK = 1_000


def upgrade() -> None:
    op.add_column(
        "transactions", sa.Column("street_search", sa.String(length=300), nullable=True)
    )

    conn = op.get_bind()
    ruas = [
        row[0]
        for row in conn.execute(sa.text("SELECT DISTINCT street FROM transactions"))
        if row[0]
    ]

    # Um UPDATE por rua faria 9 mil varreduras da tabela inteira: não há índice
    # em `street`. O mapa (rua -> chave) entra uma vez numa tabela auxiliar
    # indexada e o backfill vira uma passada só.
    mapa = op.create_table(
        "_street_search_map",
        sa.Column("street", sa.String(length=300), primary_key=True),
        sa.Column("chave", sa.String(length=300)),
    )
    linhas = [{"street": rua, "chave": street_search_text(rua)} for rua in ruas]
    for start in range(0, len(linhas), INSERT_CHUNK):
        conn.execute(mapa.insert(), linhas[start : start + INSERT_CHUNK])

    conn.execute(
        sa.text(
            "UPDATE transactions SET street_search = ("
            "  SELECT chave FROM _street_search_map m WHERE m.street = transactions.street"
            ")"
        )
    )
    op.drop_table("_street_search_map")

    # O índice depois do backfill: preencher a coluna com ele de pé custa uma
    # reescrita de índice por linha.
    op.create_index("ix_transactions_street_search", "transactions", ["street_search"])


def downgrade() -> None:
    op.drop_index("ix_transactions_street_search", table_name="transactions")
    op.drop_column("transactions", "street_search")
