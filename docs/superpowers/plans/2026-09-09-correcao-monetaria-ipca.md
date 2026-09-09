# Correção monetária pelo IPCA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar cada quitação de ITBI também em reais de hoje, corrigida pelo IPCA, sem tocar em nenhum número que já alimenta referência, fator de calibração ou nota de oportunidade.

**Architecture:** Quatro camadas independentes. A série 433 do SGS/BCB é baixada e gravada como variação mensal crua (`monetary_index`); um `Deflator` puro transforma essa série em fator de correção por mês; um cache com TTL entrega o deflator pronto às rotas; e os schemas ganham campos corrigidos **ao lado** dos nominais. O valor nominal continua sendo a única verdade gravada — o corrigido é sempre saída.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, Pydantic v2, Typer (CLI), pytest, JS puro sem framework no `app/static/`.

**Spec:** `docs/superpowers/specs/2026-09-09-correcao-monetaria-ipca-design.md`

## Global Constraints

- **Mês sem índice devolve `None`, nunca `1.0`.** Vale para quitação anterior ao início da série e para mês ainda não publicado. É a mesma regra do fator de calibração: sem medida, não inventa.
- **Convenção do deflator (Calculadora do Cidadão):** corrigir de `M` até `R` aplica a variação dos meses em `(M, R]`. A variação do próprio mês da quitação **não** entra. `fator(referencia) == 1.0`.
- **Competência é sempre dia 1** do mês (`date(ano, mes, 1)`), tanto na tabela quanto nas consultas.
- **Nada de `on_conflict_do_update`** neste trabalho: é exclusivo do dialeto Postgres e os testes rodam em SQLite in-memory (`tests/conftest.py:18`). São ~223 linhas na tabela inteira; ler e decidir em Python é portátil e sobra desempenho.
- **Nenhum request HTTP em teste.** Toda rede é substituída por `monkeypatch`; o fator conhecido entra como fixture.
- **`/leilao` e `/oportunidades` não recebem campo corrigido** nesta rodada. Lá o número entra em decisão de compra e conversa com o fator de calibração já validado.
- **Rótulo na interface é sempre "corrigido pelo IPCA"**, nunca "valor de mercado".
- Comentários e mensagens de commit em português, seguindo o repositório. Comentário explica *por quê*, não *o quê*.
- Rodar testes com `.venv/bin/pytest`. A migration roda com `PYTHONPATH=. .venv/bin/alembic upgrade head`.

## File Structure

| arquivo | responsabilidade |
| --- | --- |
| `app/models/monetary_index.py` | tabela `monetary_index`: uma variação mensal por série |
| `alembic/versions/0023_monetary_index.py` | cria a tabela |
| `app/ingestion/bcb_sgs.py` | fala com o SGS e devolve `IndexPoint`; não conhece banco |
| `app/services/monetary_index_sync.py` | grava/atualiza os pontos; não conhece HTTP |
| `app/domain/monetary_correction.py` | `Deflator` puro: série → fator. Sem I/O |
| `app/services/deflator.py` | carrega o `Deflator` do banco e cacheia com TTL |
| `app/schemas/transaction.py` | campos corrigidos em `TransactionOut`/`TransactionList` |
| `app/schemas/property.py` | campos corrigidos na linha do tempo e no resumo |
| `app/schemas/stats.py` | mediana corrigida em rua e bairro |
| `app/static/busca.js`, `property.js`, `bairro.js`, `rua.js` | exibição |

Tarefas 1–5 são backend puro e cada uma tem teste próprio. Tarefas 6–8 expõem, uma superfície por tarefa.

---

### Task 1: Tabela `monetary_index`

**Files:**
- Create: `app/models/monetary_index.py`
- Create: `alembic/versions/0023_monetary_index.py`
- Modify: `app/db/base.py` (se ele importar modelos; confira antes)
- Test: `tests/test_models/test_monetary_index.py`

**Interfaces:**
- Consumes: nada.
- Produces: `MonetaryIndex` com colunas `id: int`, `series: str`, `competencia: date`, `variacao_pct: float`; constraint única `uq_monetary_index_serie_mes` sobre `(series, competencia)`. Constante `SERIE_IPCA = "ipca"` no mesmo módulo.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models/test_monetary_index.py
"""Um mês só pode ter uma variação por série — reingerir não pode duplicar."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.monetary_index import SERIE_IPCA, MonetaryIndex


def test_grava_a_variacao_do_mes(db_session):
    db_session.add(
        MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 8, 1), variacao_pct=-0.02)
    )
    db_session.commit()
    gravado = db_session.query(MonetaryIndex).one()
    assert gravado.variacao_pct == -0.02


def test_o_mesmo_mes_da_mesma_serie_nao_entra_duas_vezes(db_session):
    for _ in range(2):
        db_session.add(
            MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 8, 1), variacao_pct=0.42)
        )
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_models/test_monetary_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.monetary_index'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/models/monetary_index.py
"""A série de um índice de preços, mês a mês, como a fonte publica.

Guarda a variação percentual do mês, não o número-índice acumulado: o
acumulado depende do mês de referência escolhido, então gravá-lo congelaria
uma decisão de leitura dentro do dado. Assim a série fica auditável linha a
linha contra a fonte.
"""

from datetime import date

from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SERIE_IPCA = "ipca"


class MonetaryIndex(Base):
    __tablename__ = "monetary_index"
    __table_args__ = (
        UniqueConstraint("series", "competencia", name="uq_monetary_index_serie_mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # A coluna existe para o dia em que entrar IGP-M sem migração de dado.
    series: Mapped[str] = mapped_column(String(20), index=True)
    # Sempre dia 1: a competência é o mês, e o dia só criaria chave duplicada.
    competencia: Mapped[date] = mapped_column(Date)
    variacao_pct: Mapped[float] = mapped_column(Numeric(8, 4))
```

Confira se `app/db/base.py` mantém uma lista de imports de modelos; se mantiver, acrescente `MonetaryIndex` lá. Acrescente também o import em `tests/conftest.py` junto dos outros `# noqa: F401`, para o `create_all` conhecer a tabela.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_models/test_monetary_index.py -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Escreva a migration**

```python
# alembic/versions/0023_monetary_index.py
"""A série do IPCA, mês a mês.

A base vai de 2008 a 2026 e todo valor é impresso em reais do dia da quitação.
Sem uma série de índice gravada não há como dizer que R$ 300.000 de 2008 valem
2,7x R$ 300.000 de 2025.

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monetary_index",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series", sa.String(length=20), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("variacao_pct", sa.Numeric(8, 4), nullable=False),
        sa.UniqueConstraint("series", "competencia", name="uq_monetary_index_serie_mes"),
    )
    op.create_index("ix_monetary_index_series", "monetary_index", ["series"])


def downgrade() -> None:
    op.drop_index("ix_monetary_index_series", table_name="monetary_index")
    op.drop_table("monetary_index")
```

- [ ] **Step 6: Rode a migration e a suíte inteira**

Run: `PYTHONPATH=. .venv/bin/alembic upgrade head && .venv/bin/pytest -q`
Expected: migration aplica sem erro; suíte toda verde.

- [ ] **Step 7: Commit**

```bash
git add app/models/monetary_index.py alembic/versions/0023_monetary_index.py tests/test_models/test_monetary_index.py tests/conftest.py
git commit -m "feat: tabela para a série mensal de um índice de preços"
```

---

### Task 2: Coletor do SGS/BCB

**Files:**
- Create: `app/ingestion/bcb_sgs.py`
- Test: `tests/test_ingestion/test_bcb_sgs.py`

**Interfaces:**
- Consumes: `app.core.http_client.request(method, url, *, timeout=30)` → `requests.Response`.
- Produces:
  - `CODIGO_IPCA = 433`
  - `@dataclass(frozen=True) IndexPoint(competencia: date, variacao_pct: float)`
  - `parse_series(payload: list[dict]) -> list[IndexPoint]` — ordenada por competência
  - `fetch_series(codigo: int = CODIGO_IPCA, desde: date = date(2008, 1, 1)) -> list[IndexPoint]`

**Contexto da API (medido em 2026-09-09):** `GET https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json&dataInicial=01/01/2008` devolve `[{"data":"01/01/2024","valor":"0.42"}, ...]`. O dia é sempre `01`, o valor é a variação percentual do mês, com ponto decimal, e pode ser negativo (`"-0.02"` em agosto de 2024). Em 2026-09-09 a série tinha 223 pontos e terminava em `01/07/2026`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingestion/test_bcb_sgs.py
"""O SGS devolve texto com vírgula decimal trocada por ponto e sinal negativo."""

from datetime import date

import pytest

from app.ingestion import bcb_sgs


def test_le_data_no_formato_brasileiro_e_valor_com_ponto():
    pontos = bcb_sgs.parse_series([{"data": "01/01/2024", "valor": "0.42"}])
    assert pontos == [bcb_sgs.IndexPoint(competencia=date(2024, 1, 1), variacao_pct=0.42)]


def test_deflacao_do_mes_e_negativa():
    # Agosto de 2024 fechou em -0,02%. Perder o sinal inverteria a correção.
    pontos = bcb_sgs.parse_series([{"data": "01/08/2024", "valor": "-0.02"}])
    assert pontos[0].variacao_pct == -0.02


def test_ordena_por_competencia():
    pontos = bcb_sgs.parse_series(
        [{"data": "01/03/2024", "valor": "0.16"}, {"data": "01/01/2024", "valor": "0.42"}]
    )
    assert [p.competencia for p in pontos] == [date(2024, 1, 1), date(2024, 3, 1)]


def test_resposta_de_erro_sobe_em_vez_de_virar_serie_vazia(monkeypatch):
    # Série vazia viraria "sem índice" em silêncio, e a tela pararia de corrigir
    # sem ninguém saber por quê.
    class RespostaRuim:
        status_code = 500

        def raise_for_status(self):
            raise RuntimeError("500")

    monkeypatch.setattr(bcb_sgs.http_client, "request", lambda *a, **k: RespostaRuim())
    with pytest.raises(RuntimeError):
        bcb_sgs.fetch_series()


def test_monta_a_url_com_a_data_inicial_no_formato_do_sgs(monkeypatch):
    capturada = {}

    class Resposta:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return [{"data": "01/01/2008", "valor": "0.54"}]

    def falsa_request(method, url, **kwargs):
        capturada["url"] = url
        return Resposta()

    monkeypatch.setattr(bcb_sgs.http_client, "request", falsa_request)
    pontos = bcb_sgs.fetch_series(desde=date(2008, 1, 1))
    assert "bcdata.sgs.433" in capturada["url"]
    assert "dataInicial=01/01/2008" in capturada["url"]
    assert pontos[0].competencia == date(2008, 1, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_ingestion/test_bcb_sgs.py -v`
Expected: FAIL — `ImportError: cannot import name 'bcb_sgs'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/ingestion/bcb_sgs.py
"""A série de um índice publicada pelo Banco Central (SGS).

O SGS entrega a variação percentual do mês como texto, com o dia fixado em 01 e
sinal quando o mês fecha em deflação. Este módulo só traduz isso em objetos: não
conhece banco, e quem grava é `services/monetary_index_sync`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.core import http_client

CODIGO_IPCA = 433
BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"


@dataclass(frozen=True)
class IndexPoint:
    competencia: date
    variacao_pct: float


def parse_series(payload: list[dict]) -> list[IndexPoint]:
    pontos = [
        IndexPoint(
            competencia=datetime.strptime(item["data"], "%d/%m/%Y").date(),
            variacao_pct=float(item["valor"]),
        )
        for item in payload
    ]
    return sorted(pontos, key=lambda p: p.competencia)


def fetch_series(
    codigo: int = CODIGO_IPCA, desde: date = date(2008, 1, 1)
) -> list[IndexPoint]:
    """Baixa a série inteira desde `desde`.

    São ~223 pontos para 2008-2026: baixar tudo e reconciliar sai mais barato do
    que pedir só o que falta e ficar cego para revisão de mês já publicado — o
    IBGE revisa, e o SGS republica.
    """
    url = BASE_URL.format(codigo=codigo)
    resposta = http_client.request(
        "GET",
        f"{url}?formato=json&dataInicial={desde.strftime('%d/%m/%Y')}",
        timeout=60,
    )
    resposta.raise_for_status()
    return parse_series(resposta.json())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_ingestion/test_bcb_sgs.py -v`
Expected: PASS (5 testes)

- [ ] **Step 5: Confira contra a fonte de verdade, uma vez, à mão**

Run:
```bash
.venv/bin/python -c "
from app.ingestion.bcb_sgs import fetch_series
pontos = fetch_series()
print(len(pontos), pontos[0], pontos[-1])
"
```
Expected: algo como `223 IndexPoint(competencia=datetime.date(2008, 1, 1), ...) IndexPoint(competencia=datetime.date(2026, 7, 1), ...)`. O último mês avança com o calendário — o que importa é que o primeiro seja 01/2008 e a contagem bata com o número de meses decorridos.

- [ ] **Step 6: Commit**

```bash
git add app/ingestion/bcb_sgs.py tests/test_ingestion/test_bcb_sgs.py
git commit -m "feat: ler a série mensal de um índice no SGS do Banco Central"
```

---

### Task 3: Sincronização, comando e agendamento

**Files:**
- Create: `app/services/monetary_index_sync.py`
- Modify: `app/ingestion/cli.py` (novo comando, junto dos demais `@app.command`)
- Modify: `Makefile` (alvo `ipca`, junto de `cadastro`/`condominios`)
- Modify: `scheduler.sh` (um passo no laço)
- Test: `tests/test_services/test_monetary_index_sync.py`

**Interfaces:**
- Consumes: `IndexPoint`, `fetch_series` (Task 2); `MonetaryIndex`, `SERIE_IPCA` (Task 1).
- Produces:
  - `save_points(db: Session, series: str, points: Iterable[IndexPoint]) -> tuple[int, int]` → `(inseridos, atualizados)`
  - `sync_ipca(db: Session, desde: date = date(2008, 1, 1)) -> tuple[int, int]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services/test_monetary_index_sync.py
"""Reingerir a série tem que atualizar mês revisado, não duplicar nem ignorar."""

from datetime import date

from app.ingestion.bcb_sgs import IndexPoint
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex
from app.services import monetary_index_sync


def test_primeira_carga_insere_tudo(db_session):
    inseridos, atualizados = monetary_index_sync.save_points(
        db_session,
        SERIE_IPCA,
        [
            IndexPoint(date(2024, 1, 1), 0.42),
            IndexPoint(date(2024, 2, 1), 0.83),
        ],
    )
    assert (inseridos, atualizados) == (2, 0)
    assert db_session.query(MonetaryIndex).count() == 2


def test_mes_revisado_pelo_ibge_atualiza_a_linha_existente(db_session):
    # O IBGE revisa mês já publicado e o SGS republica. Ignorar deixaria a base
    # divergindo da fonte para sempre; inserir de novo violaria a chave única.
    monetary_index_sync.save_points(
        db_session, SERIE_IPCA, [IndexPoint(date(2024, 1, 1), 0.42)]
    )
    inseridos, atualizados = monetary_index_sync.save_points(
        db_session, SERIE_IPCA, [IndexPoint(date(2024, 1, 1), 0.45)]
    )
    assert (inseridos, atualizados) == (0, 1)
    gravado = db_session.query(MonetaryIndex).one()
    assert float(gravado.variacao_pct) == 0.45


def test_mes_sem_mudanca_nao_conta_como_atualizado(db_session):
    monetary_index_sync.save_points(
        db_session, SERIE_IPCA, [IndexPoint(date(2024, 1, 1), 0.42)]
    )
    assert monetary_index_sync.save_points(
        db_session, SERIE_IPCA, [IndexPoint(date(2024, 1, 1), 0.42)]
    ) == (0, 0)


def test_sync_ipca_grava_o_que_o_sgs_devolveu(db_session, monkeypatch):
    monkeypatch.setattr(
        monetary_index_sync,
        "fetch_series",
        lambda **kwargs: [IndexPoint(date(2024, 1, 1), 0.42)],
    )
    assert monetary_index_sync.sync_ipca(db_session) == (1, 0)
    assert db_session.query(MonetaryIndex).one().competencia == date(2024, 1, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_services/test_monetary_index_sync.py -v`
Expected: FAIL — `ImportError: cannot import name 'monetary_index_sync'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/monetary_index_sync.py
"""Põe a série do índice no banco, reconciliando com o que já está lá.

Sem `on_conflict_do_update` de propósito: ele é exclusivo do dialeto Postgres e
os testes rodam em SQLite. A série inteira tem ~223 linhas, então ler o que
existe e decidir em Python custa nada e roda nos dois bancos.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.bcb_sgs import CODIGO_IPCA, IndexPoint, fetch_series
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex


def save_points(
    db: Session, series: str, points: Iterable[IndexPoint]
) -> tuple[int, int]:
    """Grava os pontos e devolve `(inseridos, atualizados)`."""
    existentes = {
        linha.competencia: linha
        for linha in db.scalars(
            select(MonetaryIndex).where(MonetaryIndex.series == series)
        )
    }

    inseridos = atualizados = 0
    for ponto in points:
        linha = existentes.get(ponto.competencia)
        if linha is None:
            db.add(
                MonetaryIndex(
                    series=series,
                    competencia=ponto.competencia,
                    variacao_pct=ponto.variacao_pct,
                )
            )
            inseridos += 1
        elif float(linha.variacao_pct) != ponto.variacao_pct:
            linha.variacao_pct = ponto.variacao_pct
            atualizados += 1
    db.commit()
    return inseridos, atualizados


def sync_ipca(db: Session, desde: date = date(2008, 1, 1)) -> tuple[int, int]:
    pontos = fetch_series(codigo=CODIGO_IPCA, desde=desde)
    return save_points(db, SERIE_IPCA, pontos)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_services/test_monetary_index_sync.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Adicione o comando de linha**

Em `app/ingestion/cli.py`, junto do import de `sync_registry`, acrescente
`from app.services.monetary_index_sync import sync_ipca`, e o comando:

```python
@app.command("ipca")
def ipca(
    desde: str = typer.Option("2008-01-01", help="Primeiro mês a baixar (AAAA-MM-DD)."),
) -> None:
    """Baixa a série do IPCA no Banco Central e grava as variações mensais.

    Roda quantas vezes quiser: mês revisado pelo IBGE é atualizado, mês igual é
    ignorado.
    """
    with SessionLocal() as db:
        inseridos, atualizados = sync_ipca(db, desde=date.fromisoformat(desde))
        typer.echo(f"IPCA: {inseridos} meses novos, {atualizados} revisados")
```

Confira no topo do arquivo como as outras funções abrem sessão (`SessionLocal` ou `get_db`) e se `date` já está importado; siga o que estiver lá em vez de inventar outro jeito.

- [ ] **Step 6: Adicione o alvo do Makefile**

Junto de `cadastro` e `condominios`, no mesmo estilo (comentário `##` é o que aparece no `make help`):

```makefile
## ipca: baixa a série do IPCA no Banco Central (corrige os valores para hoje)
.PHONY: ipca
ipca:
	$(CLI) ipca
```

- [ ] **Step 7: Adicione o passo no scheduler**

Em `scheduler.sh`, dentro do laço `while true`, antes da varredura de anúncios:

```sh
log "atualizando a serie do IPCA"
python -m app.ingestion.cli ipca || log "IPCA falhou; a referencia fica no mes anterior"
```

Confira como os outros passos invocam a CLI dentro do arquivo e use a mesma forma. O `||` é deliberado: BCB fora do ar não pode derrubar a coleta de anúncios, e a consequência é só a referência ficar um mês para trás.

- [ ] **Step 8: Rode de verdade, contra o banco local**

Run: `make ipca`
Expected: `IPCA: 223 meses novos, 0 revisados` (o número cresce com o calendário). Rode o mesmo comando de novo:
Expected: `IPCA: 0 meses novos, 0 revisados` — a segunda execução não pode mexer em nada.

- [ ] **Step 9: Commit**

```bash
git add app/services/monetary_index_sync.py app/ingestion/cli.py Makefile scheduler.sh tests/test_services/test_monetary_index_sync.py
git commit -m "feat: sincronizar a série do IPCA, com make ipca e passo no scheduler"
```

---

### Task 4: O `Deflator`

**Files:**
- Create: `app/domain/monetary_correction.py`
- Test: `tests/test_domain/test_monetary_correction.py`

**Interfaces:**
- Consumes: `IndexPoint` (Task 2) — ou qualquer sequência de `(competencia, variacao_pct)`.
- Produces:
  - `Deflator.from_points(points: Iterable[IndexPoint]) -> Deflator`
  - `Deflator.referencia: date` — o último mês da série
  - `Deflator.fator(competencia: date) -> float | None`
  - `Deflator.corrigir(valor: float | None, competencia: date) -> float | None`
  - `competencia_de(dia: date) -> date` — normaliza qualquer data para o dia 1 do mês

- [ ] **Step 1: Write the failing test**

```python
# tests/test_domain/test_monetary_correction.py
"""O fator que traz um valor antigo para o mês de referência.

Os números conferidos aqui saem da série 433 do SGS baixada em 2026-09-09 e da
convenção da Calculadora do Cidadão: a variação do mês inicial não entra.
"""

from datetime import date

import pytest

from app.ingestion.bcb_sgs import IndexPoint
from app.domain.monetary_correction import Deflator, competencia_de


@pytest.fixture()
def deflator() -> Deflator:
    # Três meses de 10%: de jan a abr acumula 1,331; de fev a abr, 1,21.
    return Deflator.from_points(
        [
            IndexPoint(date(2024, 1, 1), 0.0),
            IndexPoint(date(2024, 2, 1), 10.0),
            IndexPoint(date(2024, 3, 1), 10.0),
            IndexPoint(date(2024, 4, 1), 10.0),
        ]
    )


def test_a_referencia_e_o_ultimo_mes_da_serie(deflator):
    assert deflator.referencia == date(2024, 4, 1)


def test_o_mes_de_referencia_vale_um(deflator):
    assert deflator.fator(date(2024, 4, 1)) == pytest.approx(1.0)


def test_a_variacao_do_proprio_mes_da_quitacao_nao_entra(deflator):
    # Quitou em fevereiro: corrige por março e abril, não por fevereiro.
    assert deflator.fator(date(2024, 2, 1)) == pytest.approx(1.21)


def test_acumula_do_primeiro_mes(deflator):
    assert deflator.fator(date(2024, 1, 1)) == pytest.approx(1.331)


def test_mes_anterior_ao_inicio_da_serie_nao_tem_fator(deflator):
    assert deflator.fator(date(2007, 12, 1)) is None


def test_mes_ainda_nao_publicado_nao_tem_fator(deflator):
    # Nunca 1,0: sem medida, não inventa.
    assert deflator.fator(date(2024, 5, 1)) is None


def test_corrigir_aplica_o_fator(deflator):
    assert deflator.corrigir(100_000, date(2024, 2, 1)) == pytest.approx(121_000)


def test_corrigir_sem_fator_devolve_none(deflator):
    assert deflator.corrigir(100_000, date(2024, 5, 1)) is None


def test_corrigir_valor_nulo_devolve_none(deflator):
    assert deflator.corrigir(None, date(2024, 2, 1)) is None


def test_a_data_da_quitacao_vira_o_primeiro_dia_do_mes():
    assert competencia_de(date(2024, 2, 29)) == date(2024, 2, 1)


def test_corrigir_aceita_a_data_exata_da_quitacao(deflator):
    assert deflator.corrigir(100_000, date(2024, 2, 17)) == pytest.approx(121_000)


def test_serie_vazia_nao_vira_deflator():
    with pytest.raises(ValueError):
        Deflator.from_points([])


def test_fator_conhecido_do_ipca():
    # jun/2019 -> jul/2026 mede 1,469 na série real. O teste usa a variação
    # equivalente em vez da rede: o que se prova aqui é a aritmética.
    pontos = [IndexPoint(date(2019, 6, 1), 0.0)]
    acumulado = 1.469 ** (1 / 85)  # 85 meses de jul/2019 a jul/2026
    mes = date(2019, 7, 1)
    for _ in range(85):
        pontos.append(IndexPoint(mes, (acumulado - 1) * 100))
        ano, m = divmod(mes.year * 12 + mes.month, 12)
        mes = date(ano, m + 1, 1) if m + 1 <= 12 else date(ano + 1, 1, 1)
    deflator = Deflator.from_points(pontos)
    assert deflator.fator(date(2019, 6, 1)) == pytest.approx(1.469, rel=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_domain/test_monetary_correction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.monetary_correction'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/domain/monetary_correction.py
"""Trazer um valor antigo para o mês de referência.

A série guarda variação mensal; o fator entre dois meses é o produto das
variações no intervalo. A convenção é a da Calculadora do Cidadão do Banco
Central: corrigir de M até R aplica a variação dos meses em (M, R] — a variação
do próprio mês da quitação não entra. Fixar isso em um lugar só importa: sem
convenção declarada, dois pontos do código dariam números diferentes para o
mesmo ITBI e ninguém saberia qual está certo.

Mês sem índice devolve None, nunca 1,0. É a mesma regra do fator de calibração
das oportunidades: sem medida, não inventa.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date


def competencia_de(dia: date) -> date:
    """Qualquer data vira o primeiro dia do seu mês."""
    return date(dia.year, dia.month, 1)


@dataclass(frozen=True)
class Deflator:
    referencia: date
    # Mês -> índice acumulado incluindo a variação do próprio mês.
    _acumulado: dict[date, float]

    @classmethod
    def from_points(cls, points: Iterable) -> Deflator:
        ordenados = sorted(points, key=lambda p: p.competencia)
        if not ordenados:
            raise ValueError("Série vazia: não há como corrigir valor nenhum.")
        acumulado: dict[date, float] = {}
        corrente = 1.0
        for ponto in ordenados:
            corrente *= 1 + float(ponto.variacao_pct) / 100
            acumulado[ponto.competencia] = corrente
        return cls(referencia=ordenados[-1].competencia, _acumulado=acumulado)

    def fator(self, competencia: date) -> float | None:
        mes = competencia_de(competencia)
        base = self._acumulado.get(mes)
        if base is None:
            return None
        return self._acumulado[self.referencia] / base

    def corrigir(self, valor: float | None, competencia: date) -> float | None:
        if valor is None:
            return None
        fator = self.fator(competencia)
        return None if fator is None else float(valor) * fator
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_domain/test_monetary_correction.py -v`
Expected: PASS (13 testes)

- [ ] **Step 5: Confira contra a série real, uma vez**

Run:
```bash
.venv/bin/python -c "
from datetime import date
from app.ingestion.bcb_sgs import fetch_series
from app.domain.monetary_correction import Deflator
d = Deflator.from_points(fetch_series())
print('referência', d.referencia)
for ano in (2008, 2016, 2019, 2025):
    print(ano, round(d.fator(date(ano, 6, 1)), 3))
"
```
Expected, com referência 07/2026: `2008 2.705`, `2016 1.632`, `2019 1.469`, `2025 1.047`. Se a referência tiver avançado, os fatores sobem um pouco — o que não pode acontecer é ordem de grandeza diferente ou `None`.

- [ ] **Step 6: Commit**

```bash
git add app/domain/monetary_correction.py tests/test_domain/test_monetary_correction.py
git commit -m "feat: deflator que traz um valor antigo para o mês de referência"
```

---

### Task 5: Carregar o deflator uma vez, não a cada request

**Files:**
- Create: `app/services/deflator.py`
- Test: `tests/test_services/test_deflator.py`

**Interfaces:**
- Consumes: `Deflator` (Task 4), `MonetaryIndex`/`SERIE_IPCA` (Task 1).
- Produces:
  - `carregar_deflator(db: Session, series: str = SERIE_IPCA) -> Deflator | None`
  - `invalidar_cache() -> None`
  - `TTL_SEGUNDOS = 3600`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services/test_deflator.py
"""O deflator vem do banco uma vez e fica em memória — é dado que muda por mês."""

from datetime import date

from app.models.monetary_index import SERIE_IPCA, MonetaryIndex
from app.services import deflator as servico


def _semear(db_session):
    db_session.add_all(
        [
            MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 1, 1), variacao_pct=0.0),
            MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 2, 1), variacao_pct=10.0),
        ]
    )
    db_session.commit()


def test_monta_o_deflator_do_que_esta_gravado(db_session):
    servico.invalidar_cache()
    _semear(db_session)
    d = servico.carregar_deflator(db_session)
    assert d.referencia == date(2024, 2, 1)
    assert d.fator(date(2024, 1, 1)) == 1.1


def test_sem_serie_gravada_devolve_none(db_session):
    servico.invalidar_cache()
    # Antes do primeiro `make ipca` a tabela está vazia: a tela mostra só o
    # nominal em vez de quebrar.
    assert servico.carregar_deflator(db_session) is None


def test_a_segunda_chamada_nao_consulta_o_banco_de_novo(db_session):
    servico.invalidar_cache()
    _semear(db_session)
    primeiro = servico.carregar_deflator(db_session)
    db_session.add(
        MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 3, 1), variacao_pct=10.0)
    )
    db_session.commit()
    assert servico.carregar_deflator(db_session) is primeiro


def test_invalidar_cache_faz_reler(db_session):
    servico.invalidar_cache()
    _semear(db_session)
    servico.carregar_deflator(db_session)
    db_session.add(
        MonetaryIndex(series=SERIE_IPCA, competencia=date(2024, 3, 1), variacao_pct=10.0)
    )
    db_session.commit()
    servico.invalidar_cache()
    assert servico.carregar_deflator(db_session).referencia == date(2024, 3, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_services/test_deflator.py -v`
Expected: FAIL — `ImportError: cannot import name 'deflator'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/deflator.py
"""O deflator pronto para as rotas, lido do banco uma vez por hora.

A série muda uma vez por mês e o `Deflator` é imutável, então ler a tabela a
cada request seria uma consulta por página para um dado que não se move. O TTL
existe só para o processo enxergar o `make ipca` do dia sem precisar de deploy.
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.monetary_correction import Deflator
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex

TTL_SEGUNDOS = 3600

_cache: dict[str, tuple[float, Deflator | None]] = {}


def invalidar_cache() -> None:
    _cache.clear()


def carregar_deflator(db: Session, series: str = SERIE_IPCA) -> Deflator | None:
    """O deflator da série, ou `None` enquanto a tabela estiver vazia."""
    agora = time.monotonic()
    guardado = _cache.get(series)
    if guardado is not None and agora - guardado[0] < TTL_SEGUNDOS:
        return guardado[1]

    linhas = list(
        db.scalars(select(MonetaryIndex).where(MonetaryIndex.series == series))
    )
    deflator = Deflator.from_points(linhas) if linhas else None
    _cache[series] = (agora, deflator)
    return deflator
```

`MonetaryIndex` tem `competencia` e `variacao_pct`, que é exatamente o que
`Deflator.from_points` lê — por isso as linhas do banco entram direto, sem
converter para `IndexPoint`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_services/test_deflator.py -v`
Expected: PASS (4 testes)

- [ ] **Step 5: Commit**

```bash
git add app/services/deflator.py tests/test_services/test_deflator.py
git commit -m "feat: deflator carregado do banco uma vez por hora"
```

---

### Task 6: Valor corrigido na `/busca`

**Files:**
- Modify: `app/schemas/transaction.py`
- Modify: `app/api/routes/transactions.py:33-87` (`list_transactions`)
- Modify: `app/static/busca.js:247-296` (`renderTable`), `app/static/busca.js:297-336` (`renderCards`)
- Modify: `app/static/busca.html:130-140` (cabeçalho da tabela)
- Test: `tests/test_api/test_transactions.py`

**Interfaces:**
- Consumes: `carregar_deflator` (Task 5), `competencia_de` (Task 4).
- Produces: `TransactionOut.declared_value_corrected: float | None`, `TransactionOut.price_per_m2_corrected: float | None`, `TransactionList.correction_reference: date | None`.

A referência fica no envelope, não em cada item: é a mesma para a página inteira, e repeti-la 50 vezes só engordaria a resposta.

- [ ] **Step 1: Write the failing test**

```python
# acrescente ao fim de tests/test_api/test_transactions.py
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex
from app.services import deflator as servico_deflator


def _semear_ipca() -> None:
    servico_deflator.invalidar_cache()
    with Session(engine) as session:
        session.add_all(
            [
                MonetaryIndex(series=SERIE_IPCA, competencia=date(2026, 5, 1), variacao_pct=0.0),
                MonetaryIndex(series=SERIE_IPCA, competencia=date(2026, 6, 1), variacao_pct=10.0),
            ]
        )
        session.commit()


def test_a_quitacao_vem_com_o_valor_em_reais_de_hoje() -> None:
    # A linha de maio/2026 custou 300.000; junho subiu 10%.
    _semear_ipca()
    body = client.get("/transactions", params={"neighborhood": "CENTRO"}).json()
    item = body["items"][0]
    assert item["declared_value"] == 300000.0
    assert item["declared_value_corrected"] == pytest.approx(330000.0)
    assert item["price_per_m2_corrected"] == pytest.approx(330000.0 / 60)
    assert body["correction_reference"] == "2026-06-01"


def test_sem_serie_gravada_o_corrigido_vem_nulo_e_o_nominal_intacto() -> None:
    servico_deflator.invalidar_cache()
    body = client.get("/transactions", params={"neighborhood": "CENTRO"}).json()
    item = body["items"][0]
    assert item["declared_value"] == 300000.0
    assert item["declared_value_corrected"] is None
    assert body["correction_reference"] is None


def test_quitacao_em_mes_nao_publicado_nao_e_corrigida() -> None:
    # A linha de junho/2026 é do mês de referência mais um: sem índice, sem
    # correção — nunca fator 1,0 fingindo que o dinheiro não andou.
    _semear_ipca()
    with Session(engine) as session:
        session.add(
            Transaction(
                city="belo_horizonte",
                source_row_hash="hash-futuro",
                raw_address="RUA C 3 - CENTRO - 30000-000 - BELO HORIZONTE - MG",
                street="RUA C",
                street_number="3",
                complement=None,
                postal_code="30000-000",
                neighborhood="FUTURO",
                construction_year=2020,
                land_area=None,
                built_area_acquired=50.0,
                acquired_area_total=50.0,
                finish_standard="P3",
                acquired_fraction=1.0,
                construction_type="AP",
                occupation_type="RESIDENCIAL",
                declared_value=100000.0,
                calc_base_value=100000.0,
                zoning="ZA",
                settlement_date=date(2026, 7, 15),
            )
        )
        session.commit()
    body = client.get("/transactions", params={"neighborhood": "FUTURO"}).json()
    assert body["items"][0]["declared_value_corrected"] is None
```

Acrescente também `servico_deflator.invalidar_cache()` na fixture `_reset_db`, logo depois do `Base.metadata.create_all(engine)`: o cache é de módulo e vaza entre testes.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api/test_transactions.py -v -k "reais_de_hoje or corrigid"`
Expected: FAIL — `KeyError: 'declared_value_corrected'`

- [ ] **Step 3: Write minimal implementation**

Em `app/schemas/transaction.py`:

```python
class TransactionOut(BaseModel):
    ...
    created_at: datetime
    # Saída, não dado gravado: o nominal continua sendo a única verdade e a
    # única entrada da referência de preço. Nulo quando o mês da quitação não
    # tem índice publicado.
    declared_value_corrected: float | None = None
    price_per_m2_corrected: float | None = None


class TransactionList(BaseModel):
    total: int
    items: list[TransactionOut]
    # Mesma para a página inteira; repetir por item só engordaria a resposta.
    correction_reference: date | None = None
```

Em `app/api/routes/transactions.py`, importe

```python
from app.domain.monetary_correction import competencia_de
from app.services.deflator import carregar_deflator
```

e troque o `return` de `list_transactions` por:

```python
    deflator = carregar_deflator(db)
    saida = []
    for item in items:
        out = TransactionOut.model_validate(item)
        if deflator is not None:
            out.declared_value_corrected = deflator.corrigir(
                float(item.declared_value), competencia_de(item.settlement_date)
            )
            area = float(item.built_area_acquired or 0)
            if out.declared_value_corrected is not None and area > 0:
                out.price_per_m2_corrected = out.declared_value_corrected / area
        saida.append(out)
    return TransactionList(
        total=total,
        items=saida,
        correction_reference=deflator.referencia if deflator else None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api/test_transactions.py -v`
Expected: PASS — os testes novos e os 18 que já existiam.

- [ ] **Step 5: Mostre na tela**

Em `app/static/busca.js`, `renderTable`, troque as duas células de valor por célula com sub-linha — a tabela já tem 8 colunas e o padrão `cell-title`/`cell-sub` já existe na célula de endereço:

```js
    const valor = el('td', 'numeric strong');
    valor.append(el('div', 'cell-title', formatCurrency(item.declared_value)));
    if (item.declared_value_corrected != null) {
      valor.append(
        el('div', 'cell-sub', `${formatCurrency(item.declared_value_corrected)} hoje`)
      );
    }
    row.appendChild(valor);

    const m2 = el('td', 'numeric');
    m2.append(el('div', 'cell-title', formatCurrency(pricePerM2(item))));
    if (item.price_per_m2_corrected != null) {
      m2.append(el('div', 'cell-sub', `${formatCurrency(item.price_per_m2_corrected)} hoje`));
    }
    row.appendChild(m2);
```

Em `renderCards`, logo depois da linha `el('div', 'result-card-value', ...)`, acrescente a mesma leitura quando houver valor corrigido.

Em `renderScope` (`busca.js:344`), acrescente ao texto de escopo, quando `data.correction_reference` vier preenchido, a nota fixa: `valores "hoje" corrigidos pelo IPCA até <mês/ano>`. Formate o mês com `toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })`. O rótulo é "corrigido pelo IPCA" — nunca "valor de mercado".

- [ ] **Step 6: Veja rodando**

Run: `make ipca && make run`, abra `http://127.0.0.1:8000/busca`, filtre por um bairro e confirme: coluna de valor com o nominal em cima e "R$ X hoje" embaixo, e a nota do IPCA no escopo. Filtre por uma quitação de 2008 e confira que o corrigido é ~2,7x o nominal.

- [ ] **Step 7: Commit**

```bash
git add app/schemas/transaction.py app/api/routes/transactions.py app/static/busca.js app/static/busca.html tests/test_api/test_transactions.py
git commit -m "feat: /busca mostra cada quitação também em reais de hoje"
```

---

### Task 7: Linha do tempo do imóvel em reais de hoje

**Files:**
- Modify: `app/schemas/property.py`
- Modify: `app/services/property_data.py:38-70` (`to_property_out`)
- Modify: `app/api/routes/properties.py:18-33`, e o ponto onde a página `/imovel` é montada
- Modify: `app/static/property.js`
- Test: `tests/test_api/test_properties.py`

**Interfaces:**
- Consumes: `carregar_deflator` (Task 5), `Deflator`, `competencia_de` (Task 4).
- Produces: `TimelinePointOut.declared_value_corrected: float | None`, `TimelinePointOut.price_per_m2_corrected: float | None`, `PropertySummaryOut.appreciation_real_pct: float | None`, `PropertyOut.correction_reference: date | None`.

`to_property_out` ganha um parâmetro `deflator: Deflator | None = None`. Com o padrão `None`, todo chamador que ainda não passa deflator continua devolvendo exatamente o que devolve hoje.

- [ ] **Step 1: Write the failing test**

A fixture `_reset_db` do arquivo já cria a unidade `APT 1201` com duas quitações: R$ 200.000 em 2018-06-01 e R$ 300.000 em 2022-06-01 — +50% nominal. A série semeada abaixo é esparsa de propósito: o `Deflator` só precisa dos meses das pontas, e os meses ausentes exercitam o caminho "sem fator".

```python
# acrescente ao fim de tests/test_api/test_properties.py
from app.models.monetary_index import SERIE_IPCA, MonetaryIndex
from app.services import deflator as servico_deflator

PARAMS_APT = {
    "city": "belo_horizonte",
    "street": "AVE AUGUSTO DE LIMA",
    "street_number": "134",
    "complement": "AP 1201",
}


def _semear_ipca() -> None:
    """De jun/2018 a jun/2022 o índice acumula 50%: fator 1,5."""
    servico_deflator.invalidar_cache()
    with Session(engine) as session:
        session.add_all(
            [
                MonetaryIndex(series=SERIE_IPCA, competencia=date(2018, 6, 1), variacao_pct=0.0),
                MonetaryIndex(series=SERIE_IPCA, competencia=date(2022, 6, 1), variacao_pct=50.0),
            ]
        )
        session.commit()


def test_a_linha_do_tempo_traz_o_valor_em_reais_de_hoje() -> None:
    _semear_ipca()
    body = client.get("/properties", params=PARAMS_APT).json()
    por_data = {p["settlement_date"]: p for p in body["timeline"]}
    assert por_data["2018-06-01"]["declared_value_corrected"] == pytest.approx(300000.0)
    assert por_data["2022-06-01"]["declared_value_corrected"] == pytest.approx(300000.0)
    assert body["correction_reference"] == "2022-06-01"


def test_a_valorizacao_real_desconta_a_inflacao() -> None:
    # +50% nominal num período de +50% de índice é 0% real: o imóvel só
    # acompanhou o dinheiro. É essa leitura que o nominal esconde.
    _semear_ipca()
    resumo = client.get("/properties", params=PARAMS_APT).json()["summary"]
    assert resumo["appreciation_pct"] == pytest.approx(50.0)
    assert resumo["appreciation_real_pct"] == pytest.approx(0.0, abs=0.01)


def test_sem_serie_gravada_o_nominal_fica_intacto() -> None:
    servico_deflator.invalidar_cache()
    body = client.get("/properties", params=PARAMS_APT).json()
    assert body["summary"]["appreciation_pct"] == pytest.approx(50.0)
    assert body["summary"]["appreciation_real_pct"] is None
    assert body["correction_reference"] is None
    assert body["timeline"][0]["declared_value_corrected"] is None


def test_quitacao_em_mes_fora_da_serie_nao_e_corrigida() -> None:
    # A unidade APT 999 quitou em jan/2021, mês que a série semeada não tem.
    _semear_ipca()
    body = client.get(
        "/properties", params={**PARAMS_APT, "complement": "APT 999"}
    ).json()
    assert body["timeline"][0]["declared_value_corrected"] is None
```

Acrescente `servico_deflator.invalidar_cache()` na fixture `_reset_db` deste arquivo também, logo depois do `create_all`: o cache é de módulo e vaza entre testes.

**A valorização real usa as mesmas duas vendas que a nominal usa.** Leia `build_summary` em `app/domain/property_history.py:190-218` antes de implementar: `appreciation_pct` compara `full_sales[-2]` com `full_sales[-1]` — as duas últimas vendas **cheias**, não a primeira e a última da linha do tempo. A real corrige essas mesmas duas e compara as corrigidas: `(corrigida_atual / corrigida_anterior - 1) * 100`. Usar outro par produziria dois números que não conversam na mesma tela. Se qualquer uma das duas não tiver fator, o campo é `None`.

Se ao rodar o teste `appreciation_pct` não vier 50,0, a suposição sobre quais vendas contam como cheias está errada — leia `_is_partial` e ajuste a fixture, não a asserção.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api/test_properties.py -v`
Expected: FAIL — `KeyError: 'declared_value_corrected'`

- [ ] **Step 3: Write minimal implementation**

Acrescente os campos aos schemas (todos `| None = None`), dê a `to_property_out` o parâmetro `deflator: Deflator | None = None`, e dentro dele corrija ponto a ponto da linha do tempo e calcule `appreciation_real_pct` a partir das **duas últimas vendas cheias** — as mesmas que `build_summary` usa para a nominal. Na rota `/properties` e na montagem da página `/imovel`, passe `carregar_deflator(db)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api/test_properties.py -v`
Expected: PASS

- [ ] **Step 5: Mostre na tela**

Em `app/static/property.js`, na linha do tempo, imprima o corrigido como sub-linha do nominal, e no resumo mostre a valorização real ao lado da nominal, rotulada "acima da inflação". Quando `appreciation_real_pct` for nulo, some com a linha em vez de imprimir traço.

- [ ] **Step 6: Veja rodando**

Run: `make run`, abra um `/imovel` com quitações de anos distantes e confira que a valorização real é menor que a nominal.

- [ ] **Step 7: Commit**

```bash
git add app/schemas/property.py app/services/property_data.py app/api/routes/properties.py app/static/property.js tests/test_api/test_properties.py
git commit -m "feat: linha do tempo do imóvel com valor corrigido e valorização real"
```

---

### Task 8: Mediana corrigida em rua e bairro

**Files:**
- Modify: `app/domain/market_stats.py` (`NeighborhoodDetail`, `neighborhood_detail`)
- Modify: `app/domain/street_stats.py` (`StreetDetail`, `street_detail`)
- Modify: `app/schemas/stats.py` (`StreetDetailOut`, `NeighborhoodDetailOut`)
- Modify: `app/api/routes/stats.py:62-99`, `:139-...`
- Modify: `app/static/bairro.js`, `app/static/rua.js`
- Test: `tests/test_domain/test_market_stats.py`, `tests/test_domain/test_street_stats.py`

**Interfaces:**
- Consumes: `Deflator` (Task 4), `carregar_deflator` (Task 5).
- Produces: `NeighborhoodDetail.median_price_per_m2_corrected: float | None`, `StreetDetail.median_price_per_m2_corrected: float | None`, e os campos correspondentes nos schemas; `neighborhood_detail(...)` e `street_detail(...)` ganham `deflator: Deflator | None = None` como último parâmetro nomeado.

**Regra que não pode ser trocada:** cada venda é corrigida **antes** da mediana. Corrigir a mediana nominal pelo fator do mês central da janela dá outro número, e o errado — uma janela de 12 meses mistura meses com fatores diferentes. O campo nominal `median_price_per_m2` continua existindo e não muda de valor: é ele que alimenta referência, fator de calibração e nota de oportunidade.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_domain/test_market_stats.py — acrescente
from app.domain.monetary_correction import Deflator
from app.ingestion.bcb_sgs import IndexPoint

REFERENCIA = date(2026, 2, 28)


def _venda(dia: date, valor: float = 500_000) -> Sale:
    return Sale(
        neighborhood="CENTRO",
        street="RUA A",
        settlement_date=dia,
        declared_value=valor,
        built_area_acquired=100,
        construction_type="AP",
        occupation_type="RESIDENCIAL",
    )


def _deflator_jan_fev() -> Deflator:
    """Fev é a referência; jan acumula 10% até lá."""
    return Deflator.from_points(
        [IndexPoint(date(2026, 1, 1), 0.0), IndexPoint(date(2026, 2, 1), 10.0)]
    )


def test_a_mediana_corrigida_corrige_venda_a_venda():
    # Duas vendas de R$ 5.000/m², uma em jan e outra em fev. A mediana nominal
    # é 5.000; a corrigida é a mediana de (5.500, 5.000) = 5.250. Corrigir a
    # mediana pronta pelo fator do mês do meio daria outro número, e o errado.
    detalhe = neighborhood_detail(
        [_venda(date(2026, 1, 15)), _venda(date(2026, 2, 15))],
        "CENTRO",
        reference=REFERENCIA,
        months=12,
        deflator=_deflator_jan_fev(),
    )
    assert detalhe.median_price_per_m2 == pytest.approx(5_000)
    assert detalhe.median_price_per_m2_corrected == pytest.approx(5_250)


def test_sem_deflator_a_saida_e_a_de_hoje():
    # A garantia de que nenhum número já validado se move.
    detalhe = neighborhood_detail(
        [_venda(date(2026, 1, 15)), _venda(date(2026, 2, 15))],
        "CENTRO",
        reference=REFERENCIA,
        months=12,
    )
    assert detalhe.median_price_per_m2_corrected is None
    assert detalhe.median_price_per_m2 == pytest.approx(5_000)


def test_venda_sem_fator_fica_de_fora_da_mediana_corrigida():
    # Dez/2025 está fora da série. Deixar ela entrar pelo valor nominal
    # misturaria duas réguas na mesma mediana — o resultado não seria nem uma
    # coisa nem outra. A nominal continua contando as duas.
    detalhe = neighborhood_detail(
        [_venda(date(2025, 12, 15)), _venda(date(2026, 1, 15))],
        "CENTRO",
        reference=REFERENCIA,
        months=12,
        deflator=_deflator_jan_fev(),
    )
    assert detalhe.transaction_count == 2
    assert detalhe.median_price_per_m2 == pytest.approx(5_000)
    assert detalhe.median_price_per_m2_corrected == pytest.approx(5_500)
```

Escreva o teste espelho em `tests/test_domain/test_street_stats.py`, trocando
`neighborhood_detail(vendas, "CENTRO", ...)` por
`street_detail(vendas, "RUA A", reference=REFERENCIA, months=12, deflator=...)` e
mantendo as mesmas três asserções. `street_detail` filtra por `sale.street`, então
as vendas do helper já servem sem mudança.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_domain/test_market_stats.py tests/test_domain/test_street_stats.py -v`
Expected: FAIL — `TypeError: neighborhood_detail() got an unexpected keyword argument 'deflator'`

- [ ] **Step 3: Write minimal implementation**

Em `app/domain/market_stats.py`, junto de `_median_m2`:

```python
def _median_m2_corrigido(
    sales: Sequence[Sale], deflator: Deflator | None
) -> float | None:
    """Mediana do R$/m² com cada venda trazida para o mês de referência.

    Corrige venda a venda, e não a mediana pronta: a janela mistura meses com
    fatores diferentes, então aplicar um fator só à mediana responderia sobre um
    mês que não existe. Venda sem fator fica de fora — entrar pelo nominal
    misturaria duas réguas na mesma mediana.
    """
    if deflator is None:
        return None
    valores = []
    for sale in sales:
        m2 = price_per_m2(sale)
        if m2 is None:
            continue
        corrigido = deflator.corrigir(m2, competencia_de(sale.settlement_date))
        if corrigido is not None:
            valores.append(corrigido)
    return _median(valores)
```

No topo de `market_stats.py` acrescente `from app.domain.monetary_correction import Deflator, competencia_de`. Acrescente o campo aos dataclasses `NeighborhoodDetail` e `StreetDetail` (como `float | None = None`, no fim, para não quebrar construção posicional) e o parâmetro `deflator: Deflator | None = None` às duas funções de detalhe; repita a mesma função em `street_stats.py` ou importe-a de `market_stats` (`street_stats` já importa `Sale` e `price_per_m2` de lá — siga o que o arquivo já faz). Passe `carregar_deflator(db)` nas duas rotas de `app/api/routes/stats.py` e acrescente `median_price_per_m2_corrected` e `correction_reference` aos schemas.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest -q`
Expected: suíte inteira verde. Nenhum teste existente de `market_stats` ou `street_stats` pode ter mudado de número esperado — se mudou, a correção vazou para o caminho nominal e o trabalho está errado.

- [ ] **Step 5: Mostre na tela**

Em `bairro.js` e `rua.js`, imprima a mediana corrigida como segunda leitura ao lado da nominal, com o rótulo "corrigido pelo IPCA até <mês/ano>". Some com a linha quando o campo vier nulo.

- [ ] **Step 6: Veja rodando**

Run: `make run`, abra um `/bairro` e um `/rua` e confirme as duas leituras. Numa janela de 12 meses a diferença é pequena — é o esperado; a correção grande aparece na `/busca` com quitação antiga.

- [ ] **Step 7: Atualize o README**

Acrescente à tabela de páginas e à seção de metodologia: a série vem do SGS/BCB (433), a referência é o último mês publicado, a convenção exclui o mês da quitação, mês sem índice não é corrigido, e o valor nominal continua sendo a única entrada da referência de preço e da nota de oportunidade. Diga também, em uma frase, que IPCA não é preço de mercado.

- [ ] **Step 8: Commit**

```bash
git add app/domain/market_stats.py app/domain/street_stats.py app/schemas/stats.py app/api/routes/stats.py app/static/bairro.js app/static/rua.js tests/test_domain/test_market_stats.py tests/test_domain/test_street_stats.py README.md
git commit -m "feat: mediana corrigida pelo IPCA ao lado da nominal em rua e bairro"
```

---

## Verificação final

- [ ] `.venv/bin/pytest -q` — suíte inteira verde
- [ ] `PYTHONPATH=. .venv/bin/alembic upgrade head` num banco limpo, e depois `make ipca`
- [ ] `make ipca` duas vezes seguidas: a segunda reporta `0 meses novos, 0 revisados`
- [ ] Uma quitação de 2008 na `/busca` mostra corrigido ~2,7x o nominal
- [ ] Nenhum número de `/leilao` ou `/oportunidades` mudou
- [ ] `scripts/validar_referencia.py` reporta o mesmo erro mediano de antes — se mudou, a correção vazou para o caminho nominal
