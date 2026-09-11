# Simulador de Flip — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Duas telas dedicadas — `/flip` (simulador de reforma, DRE, teto MAO e matriz de sensibilidade) e `/flip/estudos` (pipeline dos estudos salvos) — sobre um motor de cálculo puro em Python.

**Architecture:** O cálculo inteiro vive em `app/domain/flip.py`, sem I/O, alimentado por premissas de custo num JSON versionado. A API expõe um endpoint de preview stateless (`POST /flips/preview`) que o front chama com debounce, mais um CRUD que grava estudos congelando um snapshot das premissas usadas. O front não calcula nada: manda entradas, recebe números prontos, formata.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (Mapped/mapped_column), Alembic, Pydantic v2, pytest + TestClient, HTML/CSS/JS sem framework (`app/static/`, design system "Escritura" em `styles.css`).

**Spec:** `docs/superpowers/specs/2026-09-11-flip-simulador-design.md`

## Global Constraints

- Português no domínio, nos nomes de campo da API e na interface. Comentários de código explicam **por quê**, não o quê — siga o tom dos arquivos vizinhos (`app/domain/appraisal.py`, `app/api/routes/auctions.py`).
- Dinheiro em `float` no domínio e `Numeric(14, 2)` no banco. Percentuais como fração (`0,15` = 15%).
- Nenhuma dependência nova. Nada de PyYAML, nada de Tailwind, nada de CDN de fonte ou de ícone.
- Premissas fixas do JSON, nunca repetidas como literal no código: ITBI 3% (`itbi_pct`), registro 1,5% (`registro_pct`), corretagem 5% (`corretagem_pct`), IR 15% (`ir_ganho_capital_pct`), contingência 15% (`contingencia_pct`), proporção de taco 70% (`proporcao_taco`), ROI alvo do MAO 18% (`roi_alvo_mao`).
- `/flip` e `/flip/estudos` são `noindex, nofollow`, ficam fora de `app/api/routes/sitemap.py` e fora do `NAV` de `app/static/common.js` — a mesma regra de `/leilao` e `/enviar`.
- Rodar testes com `.venv/bin/pytest` (ou `make test`).
- Commit a cada tarefa, em português, prefixo `feat:` / `test:` / `fix:` como no histórico.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/config/flip_premissas.json` | Tabela de custos unitários e percentuais. Fonte única dos números. |
| `app/domain/flip_premissas.py` | Carrega e valida o JSON. Não sabe calcular nada. |
| `app/domain/flip.py` | Orçamento, DRE, indicadores, MAO e matriz. Puro, sem banco. |
| `app/models/flip_study.py` | Tabela `flip_studies`. |
| `alembic/versions/0024_flip_studies.py` | Migration. |
| `app/schemas/flips.py` | Entrada e saída da API. |
| `app/services/flip_studies.py` | Banco + snapshot de premissas. Delega a conta ao domínio. |
| `app/api/routes/flips.py` | Rotas `/flips`. |
| `app/static/flip.html` / `flip.js` | Simulador. |
| `app/static/flip-estudos.html` / `flip-estudos.js` | Pipeline. |
| `app/static/styles.css` | Blocos novos no fim do arquivo: grid do simulador, KPIs, banner do MAO, heatmap. |

---

### Task 1: Premissas em JSON e seu carregador

**Files:**
- Create: `app/config/flip_premissas.json`
- Create: `app/config/__init__.py`
- Create: `app/domain/flip_premissas.py`
- Test: `tests/test_domain/test_flip_premissas.py`

**Interfaces:**
- Consumes: nada.
- Produces: `Premissa(chave: str, rotulo: str, unidade: str, valor: float)`; `Premissas` com `.valor(chave: str) -> float` e `.itens: tuple[Premissa, ...]`; `carregar_premissas(caminho: Path | None = None) -> Premissas`; `premissas_de_valores(valores: dict[str, float]) -> Premissas`; `CHAVES_OBRIGATORIAS: frozenset[str]`; `PremissaAusenteError(KeyError)`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_domain/test_flip_premissas.py
import json

import pytest

from app.domain.flip_premissas import (
    CHAVES_OBRIGATORIAS,
    PremissaAusenteError,
    carregar_premissas,
    premissas_de_valores,
)


def test_arquivo_do_repo_tem_todas_as_chaves_obrigatorias() -> None:
    premissas = carregar_premissas()
    faltando = CHAVES_OBRIGATORIAS - {item.chave for item in premissas.itens}
    assert faltando == set()


def test_valores_conhecidos_do_arquivo_do_repo() -> None:
    premissas = carregar_premissas()
    assert premissas.valor("taco") == 75.0
    assert premissas.valor("pintura_seca") == 60.0
    assert premissas.valor("coz_marcenaria") == 3000.0
    assert premissas.valor("contingencia_pct") == 0.15
    assert premissas.valor("proporcao_taco") == 0.70
    assert premissas.valor("roi_alvo_mao") == 0.18


def test_chave_desconhecida_diz_qual_chave_faltou() -> None:
    premissas = carregar_premissas()
    with pytest.raises(PremissaAusenteError) as erro:
        premissas.valor("granito_lunar")
    assert "granito_lunar" in str(erro.value)


def test_arquivo_sem_chave_obrigatoria_falha_ao_carregar(tmp_path) -> None:
    # Um arquivo capenga precisa estourar no carregamento, com o nome da chave,
    # e não virar KeyError no meio de um orçamento.
    caminho = tmp_path / "premissas.json"
    caminho.write_text(
        json.dumps([{"chave": "taco", "rotulo": "Taco", "unidade": "m2", "valor": 75}]),
        encoding="utf-8",
    )
    with pytest.raises(PremissaAusenteError) as erro:
        carregar_premissas(caminho)
    assert "contingencia_pct" in str(erro.value)


def test_premissas_de_valores_reconstroi_snapshot() -> None:
    # É assim que um estudo salvo volta a calcular com os preços de quando foi
    # salvo, mesmo que o arquivo do repo já tenha mudado.
    valores = {chave: 1.0 for chave in CHAVES_OBRIGATORIAS}
    premissas = premissas_de_valores(valores)
    assert premissas.valor("taco") == 1.0
    assert len(premissas.itens) == len(CHAVES_OBRIGATORIAS)


def test_premissas_de_valores_recusa_snapshot_incompleto() -> None:
    with pytest.raises(PremissaAusenteError):
        premissas_de_valores({"taco": 75.0})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_domain/test_flip_premissas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.flip_premissas'`

- [ ] **Step 3: Criar o arquivo de premissas**

```json
[
  {"chave": "taco", "rotulo": "Taco de madeira (raspagem + calafetação + resina)", "unidade": "m2", "valor": 75.0},
  {"chave": "pintura_seca", "rotulo": "Pintura de paredes e tetos secos", "unidade": "m2", "valor": 60.0},
  {"chave": "banho_piso", "rotulo": "Banheiro — troca de piso cerâmico/porcelanato", "unidade": "un", "valor": 450.0},
  {"chave": "banho_azulejo_box", "rotulo": "Banheiro — azulejo novo na área do box", "unidade": "un", "valor": 850.0},
  {"chave": "banho_massa_acrilica", "rotulo": "Banheiro — massa acrílica fora do box + pintura", "unidade": "un", "valor": 550.0},
  {"chave": "banho_bancada", "rotulo": "Banheiro — bancada de granito + cuba + torneira", "unidade": "un", "valor": 950.0},
  {"chave": "banho_louca", "rotulo": "Banheiro — vaso com caixa acoplada + assento + ducha", "unidade": "un", "valor": 700.0},
  {"chave": "banho_box_espelho", "rotulo": "Banheiro — box blindex padrão + espelho", "unidade": "un", "valor": 1000.0},
  {"chave": "banho_mao_obra", "rotulo": "Banheiro — mão de obra hidráulica e instalação", "unidade": "un", "valor": 800.0},
  {"chave": "banho_marcenaria", "rotulo": "Banheiro — marcenaria sob a pia (gabinete MDF)", "unidade": "un", "valor": 800.0},
  {"chave": "coz_piso", "rotulo": "Cozinha — troca de piso cerâmico/porcelanato", "unidade": "un", "valor": 1200.0},
  {"chave": "coz_azulejo", "rotulo": "Cozinha — azulejo novo na área molhada/bancada", "unidade": "un", "valor": 750.0},
  {"chave": "coz_massa_acrilica", "rotulo": "Cozinha — massa acrílica no restante das paredes + pintura", "unidade": "un", "valor": 850.0},
  {"chave": "coz_bancada", "rotulo": "Cozinha — bancada de granito com cuba inox + torneira", "unidade": "un", "valor": 1800.0},
  {"chave": "coz_mao_obra", "rotulo": "Cozinha — mão de obra hidráulica e instalações", "unidade": "un", "valor": 1100.0},
  {"chave": "coz_marcenaria", "rotulo": "Cozinha — marcenaria sob a pia (balcão/gabinete MDF)", "unidade": "un", "valor": 3000.0},
  {"chave": "eletrica_led", "rotulo": "Elétrica e iluminação LED (fixo base)", "unidade": "un", "valor": 2500.0},
  {"chave": "portas", "rotulo": "Portas e ferragens (lixamento + esmalte + maçaneta)", "unidade": "un", "valor": 200.0},
  {"chave": "cacamba", "rotulo": "Caçamba e limpeza pós-obra", "unidade": "un", "valor": 1200.0},
  {"chave": "eletrica_completa", "rotulo": "Elétrica completa — novo QDC + fiação e circuitos", "unidade": "un", "valor": 5000.0},
  {"chave": "hidraulica_completa_banheiro", "rotulo": "Hidráulica completa — banheiro (ramais e registros)", "unidade": "un", "valor": 2500.0},
  {"chave": "hidraulica_completa_cozinha", "rotulo": "Hidráulica completa — cozinha (ramais e registros)", "unidade": "un", "valor": 2000.0},
  {"chave": "contingencia_pct", "rotulo": "Contingência para imprevistos", "unidade": "pct", "valor": 0.15},
  {"chave": "proporcao_taco", "rotulo": "Proporção de área seca com taco", "unidade": "pct", "valor": 0.70},
  {"chave": "itbi_pct", "rotulo": "ITBI BH", "unidade": "pct", "valor": 0.03},
  {"chave": "registro_pct", "rotulo": "Escritura e registro", "unidade": "pct", "valor": 0.015},
  {"chave": "corretagem_pct", "rotulo": "Corretagem de venda", "unidade": "pct", "valor": 0.05},
  {"chave": "ir_ganho_capital_pct", "rotulo": "IR sobre ganho de capital", "unidade": "pct", "valor": 0.15},
  {"chave": "meses_carrego_padrao", "rotulo": "Meses de carrego padrão", "unidade": "meses", "valor": 7},
  {"chave": "condominio_mensal", "rotulo": "Condomínio mensal estimado", "unidade": "mensal", "valor": 550.0},
  {"chave": "iptu_mensal", "rotulo": "IPTU mensal estimado", "unidade": "mensal", "valor": 120.0},
  {"chave": "consumo_mensal", "rotulo": "Contas de consumo mínimas (luz/água)", "unidade": "mensal", "valor": 80.0},
  {"chave": "fator_saida_padrao", "rotulo": "Fator de saída padrão vs mediana do bairro", "unidade": "fator", "valor": 0.85},
  {"chave": "roi_alvo_mao", "rotulo": "ROI líquido alvo para cálculo de MAO", "unidade": "pct", "valor": 0.18}
]
```

`app/config/__init__.py` fica vazio (só torna o diretório um pacote, para o `Path` do módulo achá-lo em qualquer working directory).

- [ ] **Step 4: Escrever o carregador**

```python
# app/domain/flip_premissas.py
"""Os preços que alimentam o simulador de flip.

Ficam num JSON versionado, e não numa tabela: reajuste de insumo é decisão
rara, e o histórico do git conta melhor essa história que uma coluna
`updated_at`. Um estudo salvo guarda a cópia dos valores que usou, então
mudar o arquivo não mexe em conta velha.
"""

import json
from dataclasses import dataclass
from pathlib import Path

ARQUIVO_PADRAO = Path(__file__).resolve().parent.parent / "config" / "flip_premissas.json"

CHAVES_OBRIGATORIAS = frozenset(
    {
        "taco",
        "pintura_seca",
        "banho_piso",
        "banho_azulejo_box",
        "banho_massa_acrilica",
        "banho_bancada",
        "banho_louca",
        "banho_box_espelho",
        "banho_mao_obra",
        "banho_marcenaria",
        "coz_piso",
        "coz_azulejo",
        "coz_massa_acrilica",
        "coz_bancada",
        "coz_mao_obra",
        "coz_marcenaria",
        "eletrica_led",
        "portas",
        "cacamba",
        "eletrica_completa",
        "hidraulica_completa_banheiro",
        "hidraulica_completa_cozinha",
        "contingencia_pct",
        "proporcao_taco",
        "itbi_pct",
        "registro_pct",
        "corretagem_pct",
        "ir_ganho_capital_pct",
        "meses_carrego_padrao",
        "condominio_mensal",
        "iptu_mensal",
        "consumo_mensal",
        "fator_saida_padrao",
        "roi_alvo_mao",
    }
)


class PremissaAusenteError(KeyError):
    """Premissa pedida que não existe. Carrega o nome da chave na mensagem."""


@dataclass(frozen=True)
class Premissa:
    chave: str
    rotulo: str
    unidade: str
    valor: float


@dataclass(frozen=True)
class Premissas:
    itens: tuple[Premissa, ...]

    def valor(self, chave: str) -> float:
        for item in self.itens:
            if item.chave == chave:
                return item.valor
        raise PremissaAusenteError(f"premissa desconhecida: {chave}")

    def como_valores(self) -> dict[str, float]:
        """O snapshot que vai para o banco."""
        return {item.chave: item.valor for item in self.itens}


def _conferir(itens: tuple[Premissa, ...]) -> None:
    faltando = sorted(CHAVES_OBRIGATORIAS - {item.chave for item in itens})
    if faltando:
        raise PremissaAusenteError(f"premissas faltando: {', '.join(faltando)}")


def carregar_premissas(caminho: Path | None = None) -> Premissas:
    dados = json.loads((caminho or ARQUIVO_PADRAO).read_text(encoding="utf-8"))
    itens = tuple(
        Premissa(
            chave=linha["chave"],
            rotulo=linha["rotulo"],
            unidade=linha["unidade"],
            valor=float(linha["valor"]),
        )
        for linha in dados
    )
    _conferir(itens)
    return Premissas(itens=itens)


def premissas_de_valores(valores: dict[str, float]) -> Premissas:
    """Reconstrói premissas a partir do snapshot de um estudo salvo.

    O rótulo vem do arquivo atual quando a chave ainda existe lá; o valor é
    sempre o do snapshot, que é o ponto de guardá-lo.
    """
    rotulos = {item.chave: (item.rotulo, item.unidade) for item in carregar_premissas().itens}
    itens = tuple(
        Premissa(
            chave=chave,
            rotulo=rotulos.get(chave, (chave, ""))[0],
            unidade=rotulos.get(chave, (chave, ""))[1],
            valor=float(valor),
        )
        for chave, valor in sorted(valores.items())
    )
    _conferir(itens)
    return Premissas(itens=itens)
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_domain/test_flip_premissas.py -v`
Expected: PASS (6 testes)

- [ ] **Step 6: Commit**

```bash
git add app/config/ app/domain/flip_premissas.py tests/test_domain/test_flip_premissas.py
git commit -m "feat: premissas de custo do flip em JSON versionado"
```

---

### Task 2: Orçamento de obra

**Files:**
- Create: `app/domain/flip.py`
- Test: `tests/test_domain/test_flip.py`

**Interfaces:**
- Consumes: `carregar_premissas`, `Premissas` (Task 1).
- Produces: `Imovel(area_seca_m2, banheiros, cozinhas=1, portas=0, eletrica_completa=False, hidraulica_completa_banheiro=False, hidraulica_completa_cozinha=False)`; `ItemOrcamento(chave, rotulo, quantidade, custo_unitario, total)`; `GrupoOrcamento(chave, rotulo, itens, total)`; `Orcamento(grupos, subtotal, contingencia, total)`; `orcar(imovel: Imovel, premissas: Premissas) -> Orcamento`. Chaves de grupo: `areas_secas`, `banheiros`, `cozinha`, `geral`, `retrofit`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_domain/test_flip.py
import pytest

from app.domain.flip import Imovel, orcar
from app.domain.flip_premissas import carregar_premissas

PREMISSAS = carregar_premissas()

# Imóvel de referência: 92 m² secos, 2 banheiros, 1 cozinha, 6 portas.
IMOVEL = Imovel(area_seca_m2=92.0, banheiros=2, cozinhas=1, portas=6)


def _grupo(orcamento, chave):
    return next(g for g in orcamento.grupos if g.chave == chave)


def test_areas_secas_somam_taco_e_pintura() -> None:
    # 92 × 0,70 × 75 = 4.830 de taco; 92 × 60 = 5.520 de pintura.
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "areas_secas")
    assert grupo.total == pytest.approx(10_350.0)


def test_banheiro_custa_6100_por_unidade() -> None:
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "banheiros")
    assert grupo.total == pytest.approx(12_200.0)


def test_cozinha_custa_8700() -> None:
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "cozinha")
    assert grupo.total == pytest.approx(8_700.0)


def test_geral_soma_eletrica_portas_e_cacamba() -> None:
    # 2.500 + 6 × 200 + 1.200 = 4.900.
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "geral")
    assert grupo.total == pytest.approx(4_900.0)


def test_sem_retrofit_o_grupo_fica_zerado() -> None:
    grupo = _grupo(orcar(IMOVEL, PREMISSAS), "retrofit")
    assert grupo.total == 0.0
    assert grupo.itens == ()


def test_total_aplica_contingencia_sobre_o_subtotal() -> None:
    orcamento = orcar(IMOVEL, PREMISSAS)
    assert orcamento.subtotal == pytest.approx(36_150.0)
    assert orcamento.contingencia == pytest.approx(5_422.5)
    assert orcamento.total == pytest.approx(41_572.5)


def test_contingencia_nao_incide_sobre_si_mesma() -> None:
    # 36.150 × 1,15 = 41.572,50. Se a contingência entrasse no subtotal, o
    # total seria 41.572,50 × 1,15 = 47.808,38.
    orcamento = orcar(IMOVEL, PREMISSAS)
    assert orcamento.total == pytest.approx(orcamento.subtotal * 1.15)


def test_retrofit_completo_soma_os_tres_itens() -> None:
    # 5.000 de elétrica + 2.500 × 2 banheiros + 2.000 de cozinha = 12.000.
    imovel = Imovel(
        area_seca_m2=92.0,
        banheiros=2,
        cozinhas=1,
        portas=6,
        eletrica_completa=True,
        hidraulica_completa_banheiro=True,
        hidraulica_completa_cozinha=True,
    )
    orcamento = orcar(imovel, PREMISSAS)
    assert _grupo(orcamento, "retrofit").total == pytest.approx(12_000.0)
    assert orcamento.subtotal == pytest.approx(48_150.0)
    assert orcamento.total == pytest.approx(55_372.5)


def test_imovel_sem_banheiro_nao_orca_banheiro() -> None:
    orcamento = orcar(Imovel(area_seca_m2=50.0, banheiros=0, cozinhas=0, portas=0), PREMISSAS)
    assert _grupo(orcamento, "banheiros").total == 0.0
    assert _grupo(orcamento, "cozinha").total == 0.0


def test_cada_item_carrega_quantidade_e_custo_unitario() -> None:
    # A tela mostra o caderno de encargos linha a linha; sem isso ela teria de
    # refazer a conta para exibir "6 × R$ 200".
    portas = next(
        item for item in _grupo(orcar(IMOVEL, PREMISSAS), "geral").itens if item.chave == "portas"
    )
    assert portas.quantidade == 6
    assert portas.custo_unitario == pytest.approx(200.0)
    assert portas.total == pytest.approx(1_200.0)
    assert "Portas" in portas.rotulo
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.flip'`

- [ ] **Step 3: Implementar o orçamento**

```python
# app/domain/flip.py
"""Viabilidade de um flip: quanto custa a obra, o que sobra na venda, e até
quanto dá para pagar pelo imóvel.

O módulo é puro — recebe as entradas e as premissas, devolve números. Quem fala
com banco é `app/services/flip_studies.py`, e quem formata é a tela.
"""

from dataclasses import dataclass

from app.domain.flip_premissas import Premissas


@dataclass(frozen=True)
class Imovel:
    """A composição que determina o orçamento.

    `area_seca_m2` é digitada, e não derivada da área útil: banheiro e cozinha
    são orçados por unidade, então dividir a área útil exigiria inventar uma
    premissa de quantos m² cada um ocupa.
    """

    area_seca_m2: float
    banheiros: int
    cozinhas: int = 1
    portas: int = 0
    eletrica_completa: bool = False
    hidraulica_completa_banheiro: bool = False
    hidraulica_completa_cozinha: bool = False


@dataclass(frozen=True)
class ItemOrcamento:
    chave: str
    rotulo: str
    quantidade: float
    custo_unitario: float
    total: float


@dataclass(frozen=True)
class GrupoOrcamento:
    chave: str
    rotulo: str
    itens: tuple[ItemOrcamento, ...]
    total: float


@dataclass(frozen=True)
class Orcamento:
    grupos: tuple[GrupoOrcamento, ...]
    subtotal: float
    contingencia: float
    total: float


ITENS_BANHEIRO = (
    "banho_piso",
    "banho_azulejo_box",
    "banho_massa_acrilica",
    "banho_bancada",
    "banho_louca",
    "banho_box_espelho",
    "banho_mao_obra",
    "banho_marcenaria",
)

ITENS_COZINHA = (
    "coz_piso",
    "coz_azulejo",
    "coz_massa_acrilica",
    "coz_bancada",
    "coz_mao_obra",
    "coz_marcenaria",
)


def _item(premissas: Premissas, chave: str, quantidade: float) -> ItemOrcamento:
    unitario = premissas.valor(chave)
    rotulo = next(item.rotulo for item in premissas.itens if item.chave == chave)
    return ItemOrcamento(
        chave=chave,
        rotulo=rotulo,
        quantidade=quantidade,
        custo_unitario=unitario,
        total=unitario * quantidade,
    )


def _grupo(chave: str, rotulo: str, itens: tuple[ItemOrcamento, ...]) -> GrupoOrcamento:
    # Item zerado sai da lista: a tela não deve mostrar "0 × R$ 200".
    vivos = tuple(item for item in itens if item.quantidade > 0)
    return GrupoOrcamento(
        chave=chave,
        rotulo=rotulo,
        itens=vivos,
        total=sum(item.total for item in vivos),
    )


def orcar(imovel: Imovel, premissas: Premissas) -> Orcamento:
    area = max(imovel.area_seca_m2, 0.0)
    secas = _grupo(
        "areas_secas",
        "Áreas secas",
        (
            _item(premissas, "taco", area * premissas.valor("proporcao_taco")),
            _item(premissas, "pintura_seca", area),
        ),
    )
    banheiros = _grupo(
        "banheiros",
        "Banheiros",
        tuple(_item(premissas, chave, imovel.banheiros) for chave in ITENS_BANHEIRO),
    )
    cozinha = _grupo(
        "cozinha",
        "Cozinha e área de serviço",
        tuple(_item(premissas, chave, imovel.cozinhas) for chave in ITENS_COZINHA),
    )
    geral = _grupo(
        "geral",
        "Infraestrutura e serviços gerais",
        (
            _item(premissas, "eletrica_led", 1),
            _item(premissas, "portas", imovel.portas),
            _item(premissas, "cacamba", 1),
        ),
    )
    retrofit = _grupo(
        "retrofit",
        "Retrofit de infraestrutura",
        (
            _item(premissas, "eletrica_completa", 1 if imovel.eletrica_completa else 0),
            _item(
                premissas,
                "hidraulica_completa_banheiro",
                imovel.banheiros if imovel.hidraulica_completa_banheiro else 0,
            ),
            _item(
                premissas,
                "hidraulica_completa_cozinha",
                imovel.cozinhas if imovel.hidraulica_completa_cozinha else 0,
            ),
        ),
    )

    grupos = (secas, banheiros, cozinha, geral, retrofit)
    subtotal = sum(grupo.total for grupo in grupos)
    contingencia = subtotal * premissas.valor("contingencia_pct")
    return Orcamento(
        grupos=grupos,
        subtotal=subtotal,
        contingencia=contingencia,
        total=subtotal + contingencia,
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -v`
Expected: PASS (10 testes)

- [ ] **Step 5: Commit**

```bash
git add app/domain/flip.py tests/test_domain/test_flip.py
git commit -m "feat: orçamento de obra do simulador de flip"
```

---

### Task 3: DRE e indicadores

**Files:**
- Modify: `app/domain/flip.py`
- Test: `tests/test_domain/test_flip.py`

**Interfaces:**
- Consumes: `Imovel`, `orcar`, `Orcamento` (Task 2).
- Produces: `Negocio(preco_compra, arv_total, meses_carrego)`; `DRE(venda, corretagem, ganho_capital, ir_ganho_capital, preco_compra, itbi, registro, obra, carrego, lucro_liquido, capital_empatado, roi, tir_anual)`; `calcular_dre(imovel: Imovel, negocio: Negocio, premissas: Premissas, obra_total: float | None = None) -> DRE`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em tests/test_domain/test_flip.py
from app.domain.flip import Negocio, calcular_dre

NEGOCIO = Negocio(preco_compra=680_000.0, arv_total=1_080_000.0, meses_carrego=7)


def test_custos_de_aquisicao_saem_das_premissas() -> None:
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    assert dre.itbi == pytest.approx(20_400.0)  # 3% de 680.000
    assert dre.registro == pytest.approx(10_200.0)  # 1,5% de 680.000


def test_carrego_soma_condominio_iptu_e_consumo_por_mes() -> None:
    # (550 + 120 + 80) × 7 = 5.250.
    assert calcular_dre(IMOVEL, NEGOCIO, PREMISSAS).carrego == pytest.approx(5_250.0)


def test_ganho_de_capital_desconta_corretagem_obra_e_aquisicao() -> None:
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    assert dre.corretagem == pytest.approx(54_000.0)
    assert dre.ganho_capital == pytest.approx(273_827.5)
    assert dre.ir_ganho_capital == pytest.approx(41_074.125)


def test_lucro_capital_roi_e_tir_do_caso_de_referencia() -> None:
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    assert dre.obra == pytest.approx(41_572.5)
    assert dre.lucro_liquido == pytest.approx(227_503.375)
    assert dre.capital_empatado == pytest.approx(757_422.5)
    assert dre.roi == pytest.approx(0.3003652, abs=1e-6)
    assert dre.tir_anual == pytest.approx(0.5687025, abs=1e-6)


def test_prejuizo_nao_paga_imposto() -> None:
    # Comprou caro e vende barato: sem ganho, sem IR — e o lucro fica negativo.
    negocio = Negocio(preco_compra=900_000.0, arv_total=800_000.0, meses_carrego=7)
    dre = calcular_dre(IMOVEL, negocio, PREMISSAS)
    assert dre.ganho_capital < 0
    assert dre.ir_ganho_capital == 0.0
    assert dre.lucro_liquido < 0


def test_tir_de_prazo_menor_que_um_ano_anualiza_para_cima() -> None:
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    assert dre.tir_anual > dre.roi


def test_obra_pode_ser_injetada_para_nao_reorcar() -> None:
    # A matriz roda nove cenários que mudam venda e prazo, nunca a obra.
    dre = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS, obra_total=100_000.0)
    assert dre.obra == pytest.approx(100_000.0)


def test_carrego_zerado_nao_quebra_a_tir() -> None:
    # 12/0 seria divisão por zero; a TIR de prazo nulo é o próprio ROI.
    negocio = Negocio(preco_compra=680_000.0, arv_total=1_080_000.0, meses_carrego=0)
    dre = calcular_dre(IMOVEL, negocio, PREMISSAS)
    assert dre.carrego == 0.0
    assert dre.tir_anual == pytest.approx(dre.roi)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -v`
Expected: FAIL — `ImportError: cannot import name 'Negocio' from 'app.domain.flip'`

- [ ] **Step 3: Implementar o DRE**

```python
# acrescentar em app/domain/flip.py
@dataclass(frozen=True)
class Negocio:
    preco_compra: float
    arv_total: float
    meses_carrego: int


@dataclass(frozen=True)
class DRE:
    venda: float
    corretagem: float
    ganho_capital: float
    ir_ganho_capital: float
    preco_compra: float
    itbi: float
    registro: float
    obra: float
    carrego: float
    lucro_liquido: float
    capital_empatado: float
    roi: float
    tir_anual: float


def calcular_dre(
    imovel: Imovel,
    negocio: Negocio,
    premissas: Premissas,
    obra_total: float | None = None,
) -> DRE:
    """O resultado da operação inteira, do sinal à escritura de venda.

    `obra_total` existe para a matriz de sensibilidade, que varia venda e prazo
    nove vezes sobre o mesmo orçamento — reorçar a cada célula daria o mesmo
    número nove vezes.
    """
    obra = orcar(imovel, premissas).total if obra_total is None else obra_total
    compra = negocio.preco_compra
    itbi = compra * premissas.valor("itbi_pct")
    registro = compra * premissas.valor("registro_pct")
    mensal = (
        premissas.valor("condominio_mensal")
        + premissas.valor("iptu_mensal")
        + premissas.valor("consumo_mensal")
    )
    carrego = mensal * max(negocio.meses_carrego, 0)

    venda = negocio.arv_total
    corretagem = venda * premissas.valor("corretagem_pct")
    # Benfeitoria comprovada entra no custo de aquisição para efeito de ganho
    # de capital; é por isso que a obra aparece aqui e de novo no lucro.
    ganho = venda - corretagem - (compra + itbi + registro + obra)
    ir = max(ganho, 0.0) * premissas.valor("ir_ganho_capital_pct")

    lucro = venda - corretagem - ir - compra - itbi - registro - obra - carrego
    capital = compra + itbi + registro + obra + carrego
    roi = lucro / capital if capital > 0 else 0.0
    meses = max(negocio.meses_carrego, 0)
    # (1 + ROI) elevado a fração negativa estoura com ROI ≤ −100%; abaixo disso
    # o capital virou pó e anualizar não significa nada.
    if meses == 0 or roi <= -1.0:
        tir = roi
    else:
        tir = (1.0 + roi) ** (12.0 / meses) - 1.0

    return DRE(
        venda=venda,
        corretagem=corretagem,
        ganho_capital=ganho,
        ir_ganho_capital=ir,
        preco_compra=compra,
        itbi=itbi,
        registro=registro,
        obra=obra,
        carrego=carrego,
        lucro_liquido=lucro,
        capital_empatado=capital,
        roi=roi,
        tir_anual=tir,
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -v`
Expected: PASS (18 testes)

- [ ] **Step 5: Commit**

```bash
git add app/domain/flip.py tests/test_domain/test_flip.py
git commit -m "feat: DRE, ROI e TIR do simulador de flip"
```

---

### Task 4: Teto máximo de compra (MAO)

**Files:**
- Modify: `app/domain/flip.py`
- Test: `tests/test_domain/test_flip.py`

**Interfaces:**
- Consumes: `Imovel`, `Negocio`, `calcular_dre`, `orcar` (Tasks 2-3).
- Produces: `calcular_mao(imovel: Imovel, negocio: Negocio, premissas: Premissas, roi_alvo: float | None = None) -> float`. Devolve `0.0` quando nem de graça o imóvel bate o ROI alvo.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em tests/test_domain/test_flip.py
from app.domain.flip import calcular_mao


def test_comprar_no_mao_devolve_exatamente_o_roi_alvo() -> None:
    # É o teste que prova a bisseção: recalcular o DRE com o preço que ela
    # achou tem de cair em 18%.
    mao = calcular_mao(IMOVEL, NEGOCIO, PREMISSAS)
    dre = calcular_dre(IMOVEL, Negocio(mao, NEGOCIO.arv_total, NEGOCIO.meses_carrego), PREMISSAS)
    assert dre.roi == pytest.approx(0.18, abs=1e-4)


def test_mao_fica_abaixo_do_preco_quando_o_roi_atual_supera_o_alvo() -> None:
    # O caso de referência dá ROI de 30%, acima dos 18% alvo: o teto está
    # acima do preço pedido, e comprar por 680k sobra margem.
    assert calcular_mao(IMOVEL, NEGOCIO, PREMISSAS) > NEGOCIO.preco_compra


def test_mao_cai_quando_o_roi_alvo_sobe() -> None:
    exigente = calcular_mao(IMOVEL, NEGOCIO, PREMISSAS, roi_alvo=0.35)
    frouxo = calcular_mao(IMOVEL, NEGOCIO, PREMISSAS, roi_alvo=0.05)
    assert exigente < frouxo


def test_mao_cai_quando_a_obra_encarece() -> None:
    caro = Imovel(
        area_seca_m2=92.0,
        banheiros=2,
        cozinhas=1,
        portas=6,
        eletrica_completa=True,
        hidraulica_completa_banheiro=True,
        hidraulica_completa_cozinha=True,
    )
    assert calcular_mao(caro, NEGOCIO, PREMISSAS) < calcular_mao(IMOVEL, NEGOCIO, PREMISSAS)


def test_negocio_impossivel_tem_mao_zero() -> None:
    # Venda que não cobre nem a obra: não existe preço de compra positivo que
    # entregue 18%, e o teto honesto é zero.
    ruim = Negocio(preco_compra=680_000.0, arv_total=30_000.0, meses_carrego=7)
    assert calcular_mao(IMOVEL, ruim, PREMISSAS) == 0.0
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -k mao -v`
Expected: FAIL — `ImportError: cannot import name 'calcular_mao'`

- [ ] **Step 3: Implementar a bisseção**

```python
# acrescentar em app/domain/flip.py
def calcular_mao(
    imovel: Imovel,
    negocio: Negocio,
    premissas: Premissas,
    roi_alvo: float | None = None,
) -> float:
    """O maior preço de compra que ainda entrega o ROI alvo.

    Bisseção, e não fórmula fechada: o IR é `max(ganho, 0)`, e esse joelho
    quebra a linearidade em preço. O ROI cai monotonicamente conforme o preço
    sobe, então a busca converge sempre.
    """
    alvo = premissas.valor("roi_alvo_mao") if roi_alvo is None else roi_alvo
    obra = orcar(imovel, premissas).total

    def roi_de(preco: float) -> float:
        return calcular_dre(
            imovel,
            Negocio(preco, negocio.arv_total, negocio.meses_carrego),
            premissas,
            obra_total=obra,
        ).roi

    # Comprar de graça é o cenário mais generoso possível. Se nem ele bate o
    # alvo, o negócio não fecha a nenhum preço.
    if roi_de(0.0) < alvo:
        return 0.0

    baixo, alto = 0.0, max(negocio.arv_total, negocio.preco_compra) * 2.0
    if roi_de(alto) >= alvo:
        return alto
    for _ in range(80):
        meio = (baixo + alto) / 2.0
        if roi_de(meio) >= alvo:
            baixo = meio
        else:
            alto = meio
    return baixo
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -v`
Expected: PASS (23 testes)

- [ ] **Step 5: Commit**

```bash
git add app/domain/flip.py tests/test_domain/test_flip.py
git commit -m "feat: teto máximo de compra por bisseção sobre o ROI alvo"
```

---

### Task 5: Matriz de sensibilidade e simulação completa

**Files:**
- Modify: `app/domain/flip.py`
- Test: `tests/test_domain/test_flip.py`

**Interfaces:**
- Consumes: tudo das Tasks 2-4.
- Produces: `CenarioMatriz(variacao_venda, meses, venda, lucro_liquido, roi)`; `matriz_sensibilidade(imovel, negocio, premissas) -> tuple[CenarioMatriz, ...]` (9 células, ordem: variação −0,05 / 0 / +0,05 × meses 5 / 7 / 10); `Simulacao(orcamento, dre, mao, matriz)`; `simular(imovel: Imovel, negocio: Negocio, premissas: Premissas) -> Simulacao`; `VARIACOES_VENDA = (-0.05, 0.0, 0.05)`; `MESES_CENARIO = (5, 7, 10)`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em tests/test_domain/test_flip.py
from app.domain.flip import MESES_CENARIO, VARIACOES_VENDA, matriz_sensibilidade, simular


def test_matriz_tem_nove_celulas() -> None:
    assert len(matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS)) == 9


def test_matriz_cobre_todas_as_combinacoes() -> None:
    celulas = matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS)
    assert {(c.variacao_venda, c.meses) for c in celulas} == {
        (variacao, meses) for variacao in VARIACOES_VENDA for meses in MESES_CENARIO
    }


def test_celula_central_bate_com_o_cenario_base() -> None:
    # Divergência aqui significa que a matriz e o DRE discordam — o erro mais
    # caro possível, porque a tela mostraria dois números para a mesma conta.
    base = calcular_dre(IMOVEL, NEGOCIO, PREMISSAS)
    central = next(
        c
        for c in matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS)
        if c.variacao_venda == 0.0 and c.meses == NEGOCIO.meses_carrego
    )
    assert central.roi == pytest.approx(base.roi)
    assert central.lucro_liquido == pytest.approx(base.lucro_liquido)
    assert central.venda == pytest.approx(NEGOCIO.arv_total)


def test_venda_menor_e_prazo_maior_pioram_o_roi() -> None:
    celulas = {(c.variacao_venda, c.meses): c.roi for c in matriz_sensibilidade(IMOVEL, NEGOCIO, PREMISSAS)}
    assert celulas[(-0.05, 10)] < celulas[(0.0, 7)] < celulas[(0.05, 5)]


def test_simular_devolve_orcamento_dre_mao_e_matriz_coerentes() -> None:
    simulacao = simular(IMOVEL, NEGOCIO, PREMISSAS)
    assert simulacao.orcamento.total == pytest.approx(41_572.5)
    assert simulacao.dre.lucro_liquido == pytest.approx(227_503.375)
    assert simulacao.dre.obra == pytest.approx(simulacao.orcamento.total)
    assert simulacao.mao == pytest.approx(calcular_mao(IMOVEL, NEGOCIO, PREMISSAS))
    assert len(simulacao.matriz) == 9
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -k "matriz or simular" -v`
Expected: FAIL — `ImportError: cannot import name 'matriz_sensibilidade'`

- [ ] **Step 3: Implementar matriz e simulação**

```python
# acrescentar em app/domain/flip.py
VARIACOES_VENDA = (-0.05, 0.0, 0.05)
MESES_CENARIO = (5, 7, 10)


@dataclass(frozen=True)
class CenarioMatriz:
    variacao_venda: float
    meses: int
    venda: float
    lucro_liquido: float
    roi: float


@dataclass(frozen=True)
class Simulacao:
    orcamento: Orcamento
    dre: DRE
    mao: float
    matriz: tuple[CenarioMatriz, ...]


def matriz_sensibilidade(
    imovel: Imovel, negocio: Negocio, premissas: Premissas
) -> tuple[CenarioMatriz, ...]:
    """Preço de venda contra prazo: onde o negócio deixa de valer a pena.

    A obra é orçada uma vez e injetada nas nove células — nenhum cenário mexe
    na composição do imóvel.
    """
    obra = orcar(imovel, premissas).total
    celulas = []
    for variacao in VARIACOES_VENDA:
        venda = negocio.arv_total * (1.0 + variacao)
        for meses in MESES_CENARIO:
            dre = calcular_dre(
                imovel, Negocio(negocio.preco_compra, venda, meses), premissas, obra_total=obra
            )
            celulas.append(
                CenarioMatriz(
                    variacao_venda=variacao,
                    meses=meses,
                    venda=venda,
                    lucro_liquido=dre.lucro_liquido,
                    roi=dre.roi,
                )
            )
    return tuple(celulas)


def simular(imovel: Imovel, negocio: Negocio, premissas: Premissas) -> Simulacao:
    orcamento = orcar(imovel, premissas)
    return Simulacao(
        orcamento=orcamento,
        dre=calcular_dre(imovel, negocio, premissas, obra_total=orcamento.total),
        mao=calcular_mao(imovel, negocio, premissas),
        matriz=matriz_sensibilidade(imovel, negocio, premissas),
    )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_domain/ -v`
Expected: PASS (o arquivo de flip com 28 testes; os demais testes de domínio seguem verdes)

- [ ] **Step 5: Commit**

```bash
git add app/domain/flip.py tests/test_domain/test_flip.py
git commit -m "feat: matriz de sensibilidade 3x3 e simulação completa do flip"
```

---

### Task 6: Schemas e endpoint de preview

**Files:**
- Create: `app/schemas/flips.py`
- Create: `app/api/routes/flips.py`
- Modify: `app/main.py` (import e `include_router`, ao lado dos demais)
- Test: `tests/test_api/test_flips.py`

**Interfaces:**
- Consumes: `simular`, `Imovel`, `Negocio`, `carregar_premissas` (Tasks 1-5).
- Produces: schemas `FlipEntradaIn`, `ItemOrcamentoOut`, `GrupoOrcamentoOut`, `OrcamentoOut`, `DREOut`, `CenarioMatrizOut`, `SimulacaoOut`, `PremissaOut`; helper `simulacao_out(simulacao) -> SimulacaoOut`; rotas `POST /flips/preview` e `GET /flips/premissas`; `router` com `prefix="/flips"`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_api/test_flips.py
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ENTRADA = {
    "area_seca_m2": 92.0,
    "banheiros": 2,
    "cozinhas": 1,
    "portas": 6,
    "eletrica_completa": False,
    "hidraulica_completa_banheiro": False,
    "hidraulica_completa_cozinha": False,
    "preco_compra": 680000.0,
    "arv_total": 1080000.0,
    "meses_carrego": 7,
}


def test_preview_devolve_orcamento_dre_mao_e_matriz() -> None:
    resposta = client.post("/flips/preview", json=ENTRADA)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["orcamento"]["total"] == 41572.5
    assert corpo["dre"]["lucro_liquido"] == 227503.375
    assert corpo["dre"]["roi"] == pytest.approx(0.3003652, abs=1e-6)
    assert corpo["mao"] > ENTRADA["preco_compra"]
    assert len(corpo["matriz"]) == 9


def test_preview_traz_o_caderno_de_encargos_por_grupo() -> None:
    corpo = client.post("/flips/preview", json=ENTRADA).json()
    grupos = {g["chave"]: g for g in corpo["orcamento"]["grupos"]}
    assert set(grupos) == {"areas_secas", "banheiros", "cozinha", "geral", "retrofit"}
    assert grupos["banheiros"]["total"] == 12200.0
    portas = next(i for i in grupos["geral"]["itens"] if i["chave"] == "portas")
    assert portas["quantidade"] == 6
    assert portas["custo_unitario"] == 200.0


def test_preview_recusa_area_zerada() -> None:
    resposta = client.post("/flips/preview", json={**ENTRADA, "area_seca_m2": 0})
    assert resposta.status_code == 422


def test_preview_recusa_preco_negativo() -> None:
    resposta = client.post("/flips/preview", json={**ENTRADA, "preco_compra": -1})
    assert resposta.status_code == 422


def test_premissas_lista_rotulo_unidade_e_valor() -> None:
    corpo = client.get("/flips/premissas").json()
    por_chave = {item["chave"]: item for item in corpo}
    assert por_chave["taco"]["valor"] == 75.0
    assert por_chave["taco"]["unidade"] == "m2"
    assert "Taco" in por_chave["taco"]["rotulo"]
    assert por_chave["roi_alvo_mao"]["valor"] == 0.18
```

Acrescente `import pytest` no topo do arquivo — `pytest.approx` é usado acima.

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_api/test_flips.py -v`
Expected: FAIL — 404 em `/flips/preview` (rota não registrada)

- [ ] **Step 3: Escrever os schemas**

```python
# app/schemas/flips.py
from pydantic import BaseModel, ConfigDict, Field


class FlipEntradaIn(BaseModel):
    """O que a tela manda a cada mexida de campo."""

    area_seca_m2: float = Field(gt=0)
    banheiros: int = Field(ge=0, default=1)
    cozinhas: int = Field(ge=0, default=1)
    portas: int = Field(ge=0, default=0)
    eletrica_completa: bool = False
    hidraulica_completa_banheiro: bool = False
    hidraulica_completa_cozinha: bool = False
    preco_compra: float = Field(gt=0)
    arv_total: float = Field(gt=0)
    meses_carrego: int = Field(ge=0, default=7)


class ItemOrcamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chave: str
    rotulo: str
    quantidade: float
    custo_unitario: float
    total: float


class GrupoOrcamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chave: str
    rotulo: str
    itens: list[ItemOrcamentoOut]
    total: float


class OrcamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grupos: list[GrupoOrcamentoOut]
    subtotal: float
    contingencia: float
    total: float


class DREOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    venda: float
    corretagem: float
    ganho_capital: float
    ir_ganho_capital: float
    preco_compra: float
    itbi: float
    registro: float
    obra: float
    carrego: float
    lucro_liquido: float
    capital_empatado: float
    roi: float
    tir_anual: float


class CenarioMatrizOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variacao_venda: float
    meses: int
    venda: float
    lucro_liquido: float
    roi: float


class SimulacaoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orcamento: OrcamentoOut
    dre: DREOut
    mao: float
    matriz: list[CenarioMatrizOut]


class PremissaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chave: str
    rotulo: str
    unidade: str
    valor: float
```

- [ ] **Step 4: Escrever a rota**

```python
# app/api/routes/flips.py
"""Estudos de flip: quanto custa reformar, o que sobra na venda, até quanto pagar.

O preview não grava nada — é o que a tela chama a cada mexida de campo. Quem
grava é o CRUD, que congela junto a cópia das premissas usadas.
"""

from fastapi import APIRouter

from app.domain.flip import Imovel, Negocio, Simulacao, simular
from app.domain.flip_premissas import Premissas, carregar_premissas
from app.schemas.flips import FlipEntradaIn, PremissaOut, SimulacaoOut

router = APIRouter(prefix="/flips", tags=["flip"])


def imovel_de(entrada: FlipEntradaIn) -> Imovel:
    return Imovel(
        area_seca_m2=entrada.area_seca_m2,
        banheiros=entrada.banheiros,
        cozinhas=entrada.cozinhas,
        portas=entrada.portas,
        eletrica_completa=entrada.eletrica_completa,
        hidraulica_completa_banheiro=entrada.hidraulica_completa_banheiro,
        hidraulica_completa_cozinha=entrada.hidraulica_completa_cozinha,
    )


def negocio_de(entrada: FlipEntradaIn) -> Negocio:
    return Negocio(
        preco_compra=entrada.preco_compra,
        arv_total=entrada.arv_total,
        meses_carrego=entrada.meses_carrego,
    )


def simulacao_out(simulacao: Simulacao) -> SimulacaoOut:
    return SimulacaoOut.model_validate(simulacao)


def simular_entrada(entrada: FlipEntradaIn, premissas: Premissas | None = None) -> SimulacaoOut:
    usadas = premissas or carregar_premissas()
    return simulacao_out(simular(imovel_de(entrada), negocio_de(entrada), usadas))


@router.post("/preview", response_model=SimulacaoOut)
def preview(payload: FlipEntradaIn) -> SimulacaoOut:
    """Calcula sem gravar. É o que o slider chama, com debounce na tela."""
    return simular_entrada(payload)


@router.get("/premissas", response_model=list[PremissaOut])
def premissas() -> list[PremissaOut]:
    return [PremissaOut.model_validate(item) for item in carregar_premissas().itens]
```

Em `app/main.py`, junto aos demais imports de rota, acrescente
`from app.api.routes.flips import router as flips_router` e, junto aos
`include_router`, `app.include_router(flips_router)`.

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_api/test_flips.py -v`
Expected: PASS (5 testes)

- [ ] **Step 6: Commit**

```bash
git add app/schemas/flips.py app/api/routes/flips.py app/main.py tests/test_api/test_flips.py
git commit -m "feat: endpoint de preview do simulador de flip"
```

---

### Task 7: Tabela `flip_studies`

**Files:**
- Create: `app/models/flip_study.py`
- Create: `alembic/versions/0024_flip_studies.py`
- Modify: `tests/conftest.py` (registrar o modelo, como os demais)
- Test: `tests/test_models/test_flip_study.py`

**Interfaces:**
- Consumes: `app.db.base.Base`.
- Produces: `FlipStudy` com colunas `id, apelido, endereco, bairro, cidade, area_util_m2, area_seca_m2, quartos, banheiros, cozinhas, portas, preco_compra, arv_total, meses_carrego, eletrica_completa, hidraulica_completa_banheiro, hidraulica_completa_cozinha, status, origem, origem_id, premissas_json, created_at, updated_at`; `STATUS_VALIDOS = ("oportunidade", "em_analise", "descartado")`; `ORIGENS_VALIDAS = ("manual", "oportunidade", "leilao")`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# tests/test_models/test_flip_study.py
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.flip_study import FlipStudy


def _estudo(**ajustes) -> FlipStudy:
    dados = dict(
        apelido="Apto Lourdes",
        endereco="Rua Alvarenga Peixoto, 1420",
        bairro="Lourdes",
        cidade="belo_horizonte",
        area_util_m2=92.0,
        area_seca_m2=92.0,
        quartos=3,
        banheiros=2,
        cozinhas=1,
        portas=6,
        preco_compra=680000.0,
        arv_total=1080000.0,
        meses_carrego=7,
        status="oportunidade",
        origem="manual",
        premissas_json="{}",
    )
    dados.update(ajustes)
    return FlipStudy(**dados)


def test_grava_e_le_um_estudo(db_session) -> None:
    db_session.add(_estudo())
    db_session.commit()
    salvo = db_session.query(FlipStudy).one()
    assert salvo.bairro == "Lourdes"
    assert float(salvo.preco_compra) == 680000.0
    assert salvo.eletrica_completa is False


def test_status_invalido_e_recusado(db_session) -> None:
    db_session.add(_estudo(status="talvez"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_origem_invalida_e_recusada(db_session) -> None:
    db_session.add(_estudo(origem="planilha"))
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_models/test_flip_study.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.flip_study'`

- [ ] **Step 3: Escrever o modelo**

```python
# app/models/flip_study.py
"""Um estudo de flip salvo: as entradas e a cópia das premissas usadas.

Nada de lucro, ROI ou MAO em coluna: eles são função das entradas mais o
snapshot, e coluna derivada envelhece torta na primeira mudança de fórmula.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

STATUS_VALIDOS = ("oportunidade", "em_analise", "descartado")
ORIGENS_VALIDAS = ("manual", "oportunidade", "leilao")


class FlipStudy(Base):
    __tablename__ = "flip_studies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    apelido: Mapped[str | None] = mapped_column(String(150), nullable=True)
    endereco: Mapped[str] = mapped_column(String(300), nullable=False)
    bairro: Mapped[str | None] = mapped_column(String(150), nullable=True)
    cidade: Mapped[str] = mapped_column(String(150), nullable=False, default="belo_horizonte")

    area_util_m2: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    area_seca_m2: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    quartos: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    banheiros: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cozinhas: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    portas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    preco_compra: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    arv_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    meses_carrego: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    eletrica_completa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hidraulica_completa_banheiro: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    hidraulica_completa_cozinha: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="em_analise")
    # Sem chave estrangeira: o anúncio de origem pode sair do radar, e o estudo
    # não deve sair junto com ele.
    origem: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    origem_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    premissas_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('oportunidade', 'em_analise', 'descartado')",
            name="ck_flip_studies_status",
        ),
        CheckConstraint(
            "origem IN ('manual', 'oportunidade', 'leilao')",
            name="ck_flip_studies_origem",
        ),
        CheckConstraint("area_seca_m2 > 0", name="ck_flip_studies_area_seca"),
        CheckConstraint("preco_compra > 0", name="ck_flip_studies_preco"),
        CheckConstraint("meses_carrego >= 0", name="ck_flip_studies_meses"),
    )
```

Em `tests/conftest.py`, acrescente junto aos demais imports de modelo:

```python
from app.models.flip_study import FlipStudy  # noqa: F401  (registers the table)
```

- [ ] **Step 4: Escrever a migration**

```python
# alembic/versions/0024_flip_studies.py
"""Estudos de flip salvos.

O simulador calcula em memória, mas a decisão de comprar leva semanas e passa
por vários imóveis ao mesmo tempo — sem tabela, cada estudo morre no refresh.

As premissas de custo vão junto, como snapshot: elas moram num JSON versionado
no repositório, e reajustar o preço do granito não pode mexer no lucro de um
estudo fechado há seis meses.

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flip_studies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("apelido", sa.String(150), nullable=True),
        sa.Column("endereco", sa.String(300), nullable=False),
        sa.Column("bairro", sa.String(150), nullable=True),
        sa.Column("cidade", sa.String(150), nullable=False, server_default="belo_horizonte"),
        sa.Column("area_util_m2", sa.Numeric(10, 2), nullable=False),
        sa.Column("area_seca_m2", sa.Numeric(10, 2), nullable=False),
        sa.Column("quartos", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("banheiros", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cozinhas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("portas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preco_compra", sa.Numeric(14, 2), nullable=False),
        sa.Column("arv_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("meses_carrego", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("eletrica_completa", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "hidraulica_completa_banheiro", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "hidraulica_completa_cozinha", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="em_analise"),
        sa.Column("origem", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("origem_id", sa.Integer(), nullable=True),
        sa.Column("premissas_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('oportunidade', 'em_analise', 'descartado')",
            name="ck_flip_studies_status",
        ),
        sa.CheckConstraint(
            "origem IN ('manual', 'oportunidade', 'leilao')", name="ck_flip_studies_origem"
        ),
        sa.CheckConstraint("area_seca_m2 > 0", name="ck_flip_studies_area_seca"),
        sa.CheckConstraint("preco_compra > 0", name="ck_flip_studies_preco"),
        sa.CheckConstraint("meses_carrego >= 0", name="ck_flip_studies_meses"),
    )
    op.create_index("ix_flip_studies_bairro", "flip_studies", ["bairro"])
    op.create_index("ix_flip_studies_status", "flip_studies", ["status"])


def downgrade() -> None:
    op.drop_index("ix_flip_studies_status", table_name="flip_studies")
    op.drop_index("ix_flip_studies_bairro", table_name="flip_studies")
    op.drop_table("flip_studies")
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_models/test_flip_study.py -v`
Expected: PASS (3 testes)

Confira também que a migration sobe e desce, se houver banco de desenvolvimento disponível:
Run: `.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head`
Expected: sem erro. Se não houver banco configurado nesta máquina, pule este comando e siga.

- [ ] **Step 6: Commit**

```bash
git add app/models/flip_study.py alembic/versions/0024_flip_studies.py tests/conftest.py tests/test_models/test_flip_study.py
git commit -m "feat: tabela de estudos de flip com snapshot de premissas"
```

---

### Task 8: CRUD dos estudos, com snapshot congelado

**Files:**
- Create: `app/services/flip_studies.py`
- Modify: `app/schemas/flips.py`
- Modify: `app/api/routes/flips.py`
- Test: `tests/test_api/test_flips.py`

**Interfaces:**
- Consumes: `FlipStudy` (Task 7), `simular` (Task 5), `carregar_premissas` / `premissas_de_valores` (Task 1), `FlipEntradaIn` / `SimulacaoOut` (Task 6).
- Produces: schemas `FlipStudyIn`, `FlipStudyPatch`, `FlipStudyOut`, `FlipStudyListItem`; serviço com `criar(db, payload) -> FlipStudy`, `listar(db, bairro=None, status=None, preco_min=None, preco_max=None) -> list[FlipStudy]`, `buscar(db, flip_id) -> FlipStudy | None`, `editar(db, estudo, mudancas: dict, atualizar_premissas: bool) -> FlipStudy`, `remover(db, estudo) -> None`, `premissas_do(estudo) -> Premissas`, `entrada_do(estudo) -> FlipEntradaIn`, `simulacao_do(estudo) -> Simulacao`; rotas `GET/POST /flips`, `GET/PATCH/DELETE /flips/{flip_id}`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em tests/test_api/test_flips.py
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.models.flip_study import FlipStudy  # noqa: F401

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=engine)


def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _banco():
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(engine)


ESTUDO = {
    **ENTRADA,
    "apelido": "Apto Lourdes",
    "endereco": "Rua Alvarenga Peixoto, 1420",
    "bairro": "Lourdes",
    "cidade": "belo_horizonte",
    "area_util_m2": 92.0,
    "quartos": 3,
    "status": "oportunidade",
    "origem": "manual",
}


def _premissas_caras(tmp_path, monkeypatch):
    """Aponta o carregador para um arquivo com o taco quatro vezes mais caro."""
    from app.domain import flip_premissas

    original = json.loads(flip_premissas.ARQUIVO_PADRAO.read_text(encoding="utf-8"))
    for linha in original:
        if linha["chave"] == "taco":
            linha["valor"] = 300.0
    caminho = tmp_path / "premissas.json"
    caminho.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(flip_premissas, "ARQUIVO_PADRAO", caminho)


def test_criar_estudo_devolve_a_simulacao_junto() -> None:
    resposta = client.post("/flips", json=ESTUDO)
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["id"] > 0
    assert corpo["simulacao"]["dre"]["lucro_liquido"] == 227503.375
    assert corpo["bairro"] == "Lourdes"


def test_listar_traz_indicadores_recalculados() -> None:
    client.post("/flips", json=ESTUDO)
    corpo = client.get("/flips").json()
    assert len(corpo) == 1
    linha = corpo[0]
    assert linha["lucro_liquido"] == 227503.375
    assert linha["obra_total"] == 41572.5
    assert linha["mao"] > 680000.0
    assert linha["roi"] == pytest.approx(0.3003652, abs=1e-6)


def test_filtros_de_bairro_status_e_faixa_de_preco() -> None:
    client.post("/flips", json=ESTUDO)
    client.post(
        "/flips",
        json={**ESTUDO, "bairro": "Savassi", "status": "descartado", "preco_compra": 1_500_000.0},
    )
    assert len(client.get("/flips", params={"bairro": "Savassi"}).json()) == 1
    assert len(client.get("/flips", params={"status": "oportunidade"}).json()) == 1
    assert len(client.get("/flips", params={"preco_max": 700_000}).json()) == 1
    assert len(client.get("/flips", params={"preco_min": 700_000}).json()) == 1


def test_estudo_salvo_ignora_reajuste_posterior_das_premissas(tmp_path, monkeypatch) -> None:
    criado = client.post("/flips", json=ESTUDO).json()
    _premissas_caras(tmp_path, monkeypatch)
    relido = client.get(f"/flips/{criado['id']}").json()
    assert relido["simulacao"]["orcamento"]["total"] == 41572.5


def test_atualizar_premissas_traz_os_precos_novos(tmp_path, monkeypatch) -> None:
    criado = client.post("/flips", json=ESTUDO).json()
    _premissas_caras(tmp_path, monkeypatch)
    atualizado = client.patch(
        f"/flips/{criado['id']}", json={"atualizar_premissas": True}
    ).json()
    # Taco de 75 para 300: +225 × 92 × 0,7 = +14.490 no subtotal, +15% em cima.
    assert atualizado["simulacao"]["orcamento"]["total"] == pytest.approx(58_236.0)


def test_patch_muda_campo_e_recalcula() -> None:
    criado = client.post("/flips", json=ESTUDO).json()
    atualizado = client.patch(f"/flips/{criado['id']}", json={"preco_compra": 600_000.0}).json()
    assert atualizado["preco_compra"] == 600_000.0
    assert atualizado["simulacao"]["dre"]["lucro_liquido"] > 227503.375


def test_excluir_some_da_lista() -> None:
    criado = client.post("/flips", json=ESTUDO).json()
    assert client.delete(f"/flips/{criado['id']}").status_code == 204
    assert client.get("/flips").json() == []


def test_id_inexistente_da_404() -> None:
    assert client.get("/flips/999").status_code == 404
    assert client.patch("/flips/999", json={"preco_compra": 1.0}).status_code == 404
    assert client.delete("/flips/999").status_code == 404


def test_preview_nao_grava_nada() -> None:
    client.post("/flips/preview", json=ENTRADA)
    assert client.get("/flips").json() == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_api/test_flips.py -v`
Expected: FAIL — 404/405 nas rotas de CRUD

- [ ] **Step 3: Acrescentar os schemas**

```python
# acrescentar em app/schemas/flips.py
class FlipStudyIn(FlipEntradaIn):
    """Um estudo salvo: a entrada do cálculo mais a identidade do imóvel."""

    apelido: str | None = None
    endereco: str
    bairro: str | None = None
    cidade: str = "belo_horizonte"
    area_util_m2: float = Field(gt=0)
    quartos: int = Field(ge=0, default=2)
    status: str = "em_analise"
    origem: str = "manual"
    origem_id: int | None = None


class FlipStudyPatch(BaseModel):
    apelido: str | None = None
    endereco: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    area_util_m2: float | None = Field(default=None, gt=0)
    area_seca_m2: float | None = Field(default=None, gt=0)
    quartos: int | None = Field(default=None, ge=0)
    banheiros: int | None = Field(default=None, ge=0)
    cozinhas: int | None = Field(default=None, ge=0)
    portas: int | None = Field(default=None, ge=0)
    preco_compra: float | None = Field(default=None, gt=0)
    arv_total: float | None = Field(default=None, gt=0)
    meses_carrego: int | None = Field(default=None, ge=0)
    eletrica_completa: bool | None = None
    hidraulica_completa_banheiro: bool | None = None
    hidraulica_completa_cozinha: bool | None = None
    status: str | None = None
    # Não é campo do estudo: é a ordem de refazer o snapshot com os preços de
    # hoje. Fica fora do `setattr` em `editar`.
    atualizar_premissas: bool = False


class FlipStudyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    apelido: str | None
    endereco: str
    bairro: str | None
    cidade: str
    area_util_m2: float
    area_seca_m2: float
    quartos: int
    banheiros: int
    cozinhas: int
    portas: int
    preco_compra: float
    arv_total: float
    meses_carrego: int
    eletrica_completa: bool
    hidraulica_completa_banheiro: bool
    hidraulica_completa_cozinha: bool
    status: str
    origem: str
    origem_id: int | None
    simulacao: SimulacaoOut


class FlipStudyListItem(BaseModel):
    """A linha do pipeline: identidade mais os indicadores recalculados."""

    id: int
    apelido: str | None
    endereco: str
    bairro: str | None
    status: str
    area_util_m2: float
    preco_compra: float
    arv_total: float
    meses_carrego: int
    obra_total: float
    capital_empatado: float
    lucro_liquido: float
    roi: float
    tir_anual: float
    mao: float
```

- [ ] **Step 4: Escrever o serviço**

```python
# app/services/flip_studies.py
"""Estudos de flip no banco: gravar, listar, e recalcular com as premissas certas.

A conta mora em `app.domain.flip`. Aqui só entram as decisões que dependem de
persistência — em especial qual tabela de preços usar: a do estudo, e não a do
arquivo, salvo quando o dono pedir para atualizar.
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.flip import Imovel, Negocio, Simulacao, simular
from app.domain.flip_premissas import Premissas, carregar_premissas, premissas_de_valores
from app.models.flip_study import FlipStudy
from app.schemas.flips import FlipStudyIn


def premissas_do(estudo: FlipStudy) -> Premissas:
    valores = json.loads(estudo.premissas_json or "{}")
    # Estudo anterior ao snapshot, ou snapshot corrompido: cai para o arquivo
    # atual, que é melhor que quebrar a listagem inteira.
    return premissas_de_valores(valores) if valores else carregar_premissas()


def _imovel(estudo: FlipStudy) -> Imovel:
    return Imovel(
        area_seca_m2=float(estudo.area_seca_m2),
        banheiros=estudo.banheiros,
        cozinhas=estudo.cozinhas,
        portas=estudo.portas,
        eletrica_completa=estudo.eletrica_completa,
        hidraulica_completa_banheiro=estudo.hidraulica_completa_banheiro,
        hidraulica_completa_cozinha=estudo.hidraulica_completa_cozinha,
    )


def _negocio(estudo: FlipStudy) -> Negocio:
    return Negocio(
        preco_compra=float(estudo.preco_compra),
        arv_total=float(estudo.arv_total),
        meses_carrego=estudo.meses_carrego,
    )


def simulacao_do(estudo: FlipStudy) -> Simulacao:
    return simular(_imovel(estudo), _negocio(estudo), premissas_do(estudo))


def criar(db: Session, payload: FlipStudyIn) -> FlipStudy:
    premissas = carregar_premissas()
    estudo = FlipStudy(
        **payload.model_dump(),
        premissas_json=json.dumps(premissas.como_valores()),
    )
    db.add(estudo)
    db.commit()
    db.refresh(estudo)
    return estudo


def buscar(db: Session, flip_id: int) -> FlipStudy | None:
    return db.get(FlipStudy, flip_id)


def listar(
    db: Session,
    bairro: str | None = None,
    status: str | None = None,
    preco_min: float | None = None,
    preco_max: float | None = None,
) -> list[FlipStudy]:
    stmt = select(FlipStudy)
    if bairro:
        stmt = stmt.where(FlipStudy.bairro == bairro)
    if status:
        stmt = stmt.where(FlipStudy.status == status)
    if preco_min is not None:
        stmt = stmt.where(FlipStudy.preco_compra >= preco_min)
    if preco_max is not None:
        stmt = stmt.where(FlipStudy.preco_compra <= preco_max)
    stmt = stmt.order_by(FlipStudy.created_at.desc(), FlipStudy.id.desc())
    return list(db.execute(stmt).scalars())


def editar(
    db: Session, estudo: FlipStudy, mudancas: dict, atualizar_premissas: bool = False
) -> FlipStudy:
    for campo, valor in mudancas.items():
        setattr(estudo, campo, valor)
    if atualizar_premissas:
        estudo.premissas_json = json.dumps(carregar_premissas().como_valores())
    db.commit()
    db.refresh(estudo)
    return estudo


def remover(db: Session, estudo: FlipStudy) -> None:
    db.delete(estudo)
    db.commit()
```

- [ ] **Step 5: Acrescentar as rotas de CRUD**

```python
# acrescentar em app/api/routes/flips.py
from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.flip_study import FlipStudy
from app.schemas.flips import FlipStudyIn, FlipStudyListItem, FlipStudyOut, FlipStudyPatch
from app.services import flip_studies


def _estudo_out(estudo: FlipStudy) -> FlipStudyOut:
    # A simulação não é coluna; montar campo a campo evita um
    # `model_validate` que reclamaria dela como obrigatória e ausente.
    campos = {
        campo: getattr(estudo, campo)
        for campo in FlipStudyOut.model_fields
        if campo != "simulacao"
    }
    return FlipStudyOut(**campos, simulacao=simulacao_out(flip_studies.simulacao_do(estudo)))


def _linha(estudo: FlipStudy) -> FlipStudyListItem:
    simulacao = flip_studies.simulacao_do(estudo)
    return FlipStudyListItem(
        id=estudo.id,
        apelido=estudo.apelido,
        endereco=estudo.endereco,
        bairro=estudo.bairro,
        status=estudo.status,
        area_util_m2=float(estudo.area_util_m2),
        preco_compra=float(estudo.preco_compra),
        arv_total=float(estudo.arv_total),
        meses_carrego=estudo.meses_carrego,
        obra_total=simulacao.orcamento.total,
        capital_empatado=simulacao.dre.capital_empatado,
        lucro_liquido=simulacao.dre.lucro_liquido,
        roi=simulacao.dre.roi,
        tir_anual=simulacao.dre.tir_anual,
        mao=simulacao.mao,
    )


def _buscar(db: Session, flip_id: int) -> FlipStudy:
    estudo = flip_studies.buscar(db, flip_id)
    if estudo is None:
        raise HTTPException(status_code=404, detail="estudo não encontrado")
    return estudo


@router.get("", response_model=list[FlipStudyListItem])
def listar(
    bairro: str | None = Query(None),
    status: str | None = Query(None),
    preco_min: float | None = Query(None),
    preco_max: float | None = Query(None),
    db: Session = Depends(get_db),
) -> list[FlipStudyListItem]:
    return [
        _linha(estudo)
        for estudo in flip_studies.listar(db, bairro, status, preco_min, preco_max)
    ]


@router.post("", response_model=FlipStudyOut, status_code=201)
def criar(payload: FlipStudyIn, db: Session = Depends(get_db)) -> FlipStudyOut:
    return _estudo_out(flip_studies.criar(db, payload))


@router.get("/{flip_id}", response_model=FlipStudyOut)
def detalhe(flip_id: int, db: Session = Depends(get_db)) -> FlipStudyOut:
    return _estudo_out(_buscar(db, flip_id))


@router.patch("/{flip_id}", response_model=FlipStudyOut)
def editar(flip_id: int, payload: FlipStudyPatch, db: Session = Depends(get_db)) -> FlipStudyOut:
    estudo = _buscar(db, flip_id)
    mudancas = payload.model_dump(exclude_unset=True)
    atualizar = bool(mudancas.pop("atualizar_premissas", False))
    return _estudo_out(flip_studies.editar(db, estudo, mudancas, atualizar))


@router.delete("/{flip_id}", status_code=204)
def remover(flip_id: int, db: Session = Depends(get_db)) -> None:
    flip_studies.remover(db, _buscar(db, flip_id))
```

Atenção à ordem de registro: `/flips/preview` e `/flips/premissas` precisam vir **antes** de `/flips/{flip_id}` no arquivo, senão o FastAPI casa `preview` como id e devolve 422.

- [ ] **Step 6: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_api/test_flips.py -v`
Expected: PASS (14 testes)

- [ ] **Step 7: Commit**

```bash
git add app/services/flip_studies.py app/schemas/flips.py app/api/routes/flips.py tests/test_api/test_flips.py
git commit -m "feat: CRUD de estudos de flip com premissas congeladas"
```

---

### Task 9: As duas páginas no roteador, com o esqueleto do simulador

**Files:**
- Modify: `app/main.py` (dicionário `PAGES`)
- Create: `app/static/flip.html`
- Create: `app/static/flip-estudos.html`
- Modify: `app/static/styles.css` (bloco novo no fim do arquivo)
- Test: `tests/test_api/test_pages.py`

**Interfaces:**
- Consumes: `PAGES` de `app/main.py`.
- Produces: rotas `/flip` e `/flip/estudos`; ids de elemento que o JS das Tasks 10-11 consome — no simulador: `form-imovel`, `kpi-obra`, `kpi-capital`, `kpi-lucro`, `kpi-tir`, `mao-valor`, `mao-comparativo`, `orcamento`, `dre`, `matriz`, `erro`, `btn-salvar`, `btn-resetar`, `ref-bairro`; no pipeline: `filtros`, `f-bairro`, `f-status`, `f-preco-min`, `f-preco-max`, `kpis`, `tabela`, `corpo-tabela`, `vazio`.

- [ ] **Step 1: Escrever o teste que falha**

```python
# acrescentar em tests/test_api/test_pages.py
def test_flip_e_pipeline_ficam_fora_do_indice() -> None:
    # Anotação particular do dono, como /leilao: não entra em buscador.
    for path in ("/flip", "/flip/estudos"):
        resposta = client.get(path)
        assert resposta.status_code == 200
        assert "noindex" in resposta.text


def test_flip_nao_entra_no_nav_publico() -> None:
    common = Path("app/static/common.js").read_text(encoding="utf-8")
    nav = common.split("const NAV_ITEMS")[1].split("]")[0]
    assert "/flip" not in nav
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/bin/pytest tests/test_api/test_pages.py -v`
Expected: FAIL — 404 em `/flip`

- [ ] **Step 3: Registrar as rotas**

Em `app/main.py`, dentro do dicionário `PAGES`, junto das entradas privadas:

```python
    # Estudo de flip: mesma natureza de /leilao — anotação particular do dono,
    # fora do SEO e da navegação pública.
    "/flip": "flip.html",
    "/flip/estudos": "flip-estudos.html",
```

- [ ] **Step 4: Escrever `app/static/flip.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ImovelRadar — simulador de flip</title>
  <!-- Conta de margem do dono: fora do SEO e da navegação pública. -->
  <meta name="robots" content="noindex, nofollow">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main class="wrap page">
    <div class="page-head">
      <span class="eyebrow">Compra, obra e revenda</span>
      <h1 class="page-title">Simulador de flip</h1>
      <a class="btn btn-ghost btn-sm" href="/flip/estudos">Ver estudos salvos</a>
    </div>

    <p class="panel-note">
      Quanto custa a obra, o que sobra na venda, e até quanto dá para pagar pelo
      imóvel. O custo de reforma sai de uma tabela de preços por serviço, as
      quantidades saem da composição do imóvel, e o <strong>valor de saída é
      digitado por você</strong> — o simulador não arbitra por quanto o imóvel
      revende. O <strong>teto MAO</strong> é o maior preço de compra que ainda
      entrega o ROI alvo.
    </p>

    <p class="panel-note" id="erro" hidden></p>

    <div class="flip-grid">
      <form class="flip-entradas" id="form-imovel">
        <section class="panel">
          <div class="panel-head"><h2 class="section-title">Dados do imóvel</h2></div>
          <div class="form-grid">
            <div class="field field-wide">
              <label for="f-endereco">Endereço *</label>
              <input class="input" id="f-endereco" name="endereco" type="text" required
                     placeholder="Rua Alvarenga Peixoto, 1420 — apt 402">
            </div>
            <div class="field">
              <label for="f-apelido">Apelido</label>
              <input class="input" id="f-apelido" name="apelido" type="text" placeholder="Apto Lourdes">
            </div>
            <div class="field">
              <label for="f-bairro">Bairro</label>
              <input class="input" id="f-bairro" name="bairro" type="text" placeholder="Lourdes">
            </div>
            <div class="field">
              <label for="f-area-util">Área útil (m²)</label>
              <input class="input" id="f-area-util" name="area_util_m2" type="number" min="1" step="0.01" value="92">
            </div>
            <div class="field">
              <label for="f-area-seca">Área seca (m²)</label>
              <input class="input" id="f-area-seca" name="area_seca_m2" type="number" min="1" step="0.01" value="92">
              <small class="card-meta">Piso seco a reformar: sala e quartos, fora banheiros e cozinha.</small>
            </div>
            <div class="field">
              <label for="f-quartos">Quartos</label>
              <input class="input" id="f-quartos" name="quartos" type="number" min="0" step="1" value="3">
            </div>
            <div class="field">
              <label for="f-banheiros">Banheiros</label>
              <input class="input" id="f-banheiros" name="banheiros" type="number" min="0" step="1" value="2">
            </div>
            <div class="field">
              <label for="f-cozinhas">Cozinhas</label>
              <input class="input" id="f-cozinhas" name="cozinhas" type="number" min="0" step="1" value="1">
            </div>
            <div class="field">
              <label for="f-portas">Portas a trocar</label>
              <input class="input" id="f-portas" name="portas" type="number" min="0" step="1" value="6">
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2 class="section-title">Retrofit de infraestrutura</h2></div>
          <p class="panel-note">
            Prédio antigo cobra isso na revenda, de um jeito ou de outro: coluna de
            ferro galvanizado e quadro sem DR viram desconto na proposta.
          </p>
          <div class="flip-toggles">
            <label class="flip-toggle">
              <input type="checkbox" id="f-eletrica" name="eletrica_completa">
              <span>Elétrica completa — novo QDC, fiação e circuitos</span>
            </label>
            <label class="flip-toggle">
              <input type="checkbox" id="f-hidr-banheiro" name="hidraulica_completa_banheiro">
              <span>Hidráulica completa nos banheiros — ramais e registros</span>
            </label>
            <label class="flip-toggle">
              <input type="checkbox" id="f-hidr-cozinha" name="hidraulica_completa_cozinha">
              <span>Hidráulica completa na cozinha — ramais e registros</span>
            </label>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2 class="section-title">Compra e saída</h2></div>
          <div class="form-grid">
            <div class="field">
              <label for="f-preco">Preço de compra (R$)</label>
              <input class="input" id="f-preco" name="preco_compra" type="number" min="1" step="1000" value="680000">
            </div>
            <div class="field">
              <label for="f-arv">Valor de venda estimado (R$)</label>
              <input class="input" id="f-arv" name="arv_total" type="number" min="1" step="1000" value="1080000">
              <small class="card-meta" id="ref-bairro"></small>
            </div>
            <div class="field">
              <label for="f-meses">Meses de carrego</label>
              <input class="input" id="f-meses" name="meses_carrego" type="number" min="0" step="1" value="7">
            </div>
            <div class="field">
              <label for="f-status">Status</label>
              <select class="input" id="f-status" name="status">
                <option value="em_analise">Em análise</option>
                <option value="oportunidade">Oportunidade</option>
                <option value="descartado">Descartado</option>
              </select>
            </div>
          </div>
          <div class="flip-acoes">
            <button class="btn btn-secondary btn-sm" id="btn-resetar" type="button">Restaurar padrões</button>
            <button class="btn btn-petroleo" id="btn-salvar" type="submit">Salvar estudo</button>
          </div>
        </section>
      </form>

      <div class="flip-resultado">
        <section class="flip-kpis">
          <article class="card"><span class="card-label">Custo da obra</span><strong class="card-value" id="kpi-obra">—</strong><span class="card-meta" id="kpi-obra-meta"></span></article>
          <article class="card"><span class="card-label">Capital empatado</span><strong class="card-value" id="kpi-capital">—</strong><span class="card-meta">Compra + ITBI + registro + obra + carrego</span></article>
          <article class="card"><span class="card-label">Lucro líquido</span><strong class="card-value" id="kpi-lucro">—</strong><span class="card-meta" id="kpi-lucro-meta"></span></article>
          <article class="card"><span class="card-label">TIR anualizada</span><strong class="card-value" id="kpi-tir">—</strong><span class="card-meta" id="kpi-tir-meta"></span></article>
        </section>

        <section class="panel flip-mao">
          <span class="eyebrow">Teto máximo de compra</span>
          <strong class="flip-mao-valor" id="mao-valor">—</strong>
          <p class="panel-note" id="mao-comparativo"></p>
        </section>

        <section class="panel">
          <div class="panel-head"><h2 class="section-title">Caderno de encargos</h2></div>
          <div id="orcamento"></div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2 class="section-title">DRE da operação</h2></div>
          <div id="dre"></div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2 class="section-title">Sensibilidade: preço de venda × prazo</h2></div>
          <div id="matriz"></div>
        </section>
      </div>
    </div>
  </main>

  <script src="/static/common.js"></script>
  <script src="/static/flip.js"></script>
</body>
</html>
```

- [ ] **Step 5: Escrever `app/static/flip-estudos.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ImovelRadar — estudos de flip</title>
  <meta name="robots" content="noindex, nofollow">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main class="wrap page">
    <div class="page-head">
      <span class="eyebrow">Pipeline de compras potenciais</span>
      <h1 class="page-title">Estudos de flip</h1>
      <a class="btn btn-petroleo btn-sm" href="/flip">Novo estudo</a>
    </div>

    <p class="panel-note">
      Cada linha recalcula com os preços de insumo que estavam valendo quando o
      estudo foi salvo. O teto MAO ao lado do preço de compra diz, de relance,
      quais propostas ainda cabem no ROI alvo.
    </p>

    <p class="panel-note" id="erro" hidden></p>

    <section class="flip-kpis" id="kpis"></section>

    <form class="filter-bar" id="filtros">
      <div class="filter-row">
        <div class="field"><input class="input" id="f-bairro" placeholder="Todos os bairros" aria-label="Bairro"></div>
        <div class="select-wrap">
          <select id="f-status" aria-label="Status">
            <option value="">Todos os status</option>
            <option value="oportunidade">Oportunidade</option>
            <option value="em_analise">Em análise</option>
            <option value="descartado">Descartado</option>
          </select>
        </div>
        <div class="field"><input class="input" id="f-preco-min" type="number" step="10000" placeholder="Preço mínimo" aria-label="Preço mínimo"></div>
        <div class="field"><input class="input" id="f-preco-max" type="number" step="10000" placeholder="Preço máximo" aria-label="Preço máximo"></div>
      </div>
    </form>

    <section class="table-panel">
      <div class="table-wrapper">
        <table id="tabela">
          <thead>
            <tr>
              <th>Imóvel</th>
              <th>Bairro</th>
              <th class="num">Compra</th>
              <th class="num">Obra</th>
              <th class="num">Capital</th>
              <th class="num">Lucro</th>
              <th class="num">ROI</th>
              <th class="num">TIR a.a.</th>
              <th class="num">Teto MAO</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="corpo-tabela"></tbody>
        </table>
      </div>
      <div id="vazio"></div>
    </section>
  </main>

  <script src="/static/common.js"></script>
  <script src="/static/flip-estudos.js"></script>
</body>
</html>
```

- [ ] **Step 6: Acrescentar o CSS no fim de `app/static/styles.css`**

```css
/* Simulador de flip — entradas à esquerda, números à direita. A coluna de
   resultado repinta inteira a cada preview, então nada aqui pode depender de
   altura fixa. */
.flip-grid {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: var(--s5);
  align-items: start;
}

.flip-entradas,
.flip-resultado {
  display: flex;
  flex-direction: column;
  gap: var(--s4);
  min-width: 0;
}

.flip-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--s3);
}

.flip-toggles {
  display: flex;
  flex-direction: column;
  gap: var(--s2);
  padding: var(--s3) 0 0;
}

.flip-toggle {
  display: flex;
  gap: var(--s2);
  align-items: flex-start;
  font-size: 0.92rem;
  color: var(--tinta-80);
}

.flip-acoes {
  display: flex;
  justify-content: flex-end;
  gap: var(--s2);
  padding-top: var(--s3);
}

.flip-mao-valor {
  display: block;
  font-family: var(--titulo);
  font-size: 2rem;
  line-height: 1.1;
  color: var(--petroleo);
  padding: var(--s1) 0 var(--s2);
}

.flip-linha {
  display: flex;
  justify-content: space-between;
  gap: var(--s3);
  padding: var(--s2) 0;
  border-bottom: 1px solid var(--regua);
}

.flip-linha:last-child { border-bottom: none; }
.flip-linha-total { font-weight: 600; color: var(--tinta); }
.flip-linha-negativa .flip-valor { color: var(--coral-forte); }
.flip-valor { font-variant-numeric: tabular-nums; white-space: nowrap; }

.flip-grupo > summary {
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  gap: var(--s3);
  padding: var(--s2) 0;
  font-weight: 600;
  border-bottom: 1px solid var(--regua);
}

.flip-item {
  display: flex;
  justify-content: space-between;
  gap: var(--s3);
  padding: var(--s1) 0 var(--s1) var(--s4);
  font-size: 0.88rem;
  color: var(--tinta-70);
}

.flip-matriz { width: 100%; border-collapse: collapse; }
.flip-matriz th,
.flip-matriz td {
  border: 1px solid var(--regua);
  padding: var(--s2);
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.flip-matriz .flip-celula-otima { background: var(--tag-salvia-bg); color: var(--tag-salvia-fg); }
.flip-matriz .flip-celula-aceitavel { background: var(--realce); color: var(--tinta-80); }
.flip-matriz .flip-celula-risco { background: var(--tag-terracota-bg); color: var(--tag-terracota-fg); }
.flip-matriz .flip-celula-base { outline: 2px solid var(--petroleo); outline-offset: -2px; }
.flip-celula-lucro { display: block; font-size: 0.8rem; opacity: 0.85; }

@media (max-width: 900px) {
  .flip-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 7: Rodar e ver passar**

Run: `.venv/bin/pytest tests/test_api/test_pages.py -v`
Expected: PASS — inclusive os testes parametrizados por `PAGES`, que agora cobrem `/flip` e `/flip/estudos`

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/static/flip.html app/static/flip-estudos.html app/static/styles.css tests/test_api/test_pages.py
git commit -m "feat: páginas /flip e /flip/estudos com o esqueleto do simulador"
```

---

### Task 10: O simulador vivo (`flip.js`)

**Files:**
- Create: `app/static/flip.js`
- Test: verificação manual (o projeto não tem suíte de JS) — passo 3 abaixo

**Interfaces:**
- Consumes: `window.IR` (`$`, `el`, `fetchJson`, `formatCurrency`, `formatPct`, `mountChrome`, `navigate`); `POST /flips/preview`, `POST /flips`, `GET /flips/{id}`, `PATCH /flips/{id}`, `GET /neighborhoods/{bairro}` via `/stats`.
- Produces: a tela funcionando; nenhum símbolo consumido por outra task.

- [ ] **Step 1: Escrever `app/static/flip.js`**

```javascript
/* Simulador de flip: o cálculo é todo do servidor.
 *
 * A tela manda as entradas e pinta o que volta. Repetir a conta aqui daria uma
 * segunda implementação de MAO e DRE para divergir da primeira no primeiro
 * reajuste de premissa.
 */
const { API_BASE, $, el, fetchJson, formatCurrency, formatPct, mountChrome } = window.IR;

const CAMPOS_NUMERICOS = [
  'area_util_m2', 'area_seca_m2', 'quartos', 'banheiros', 'cozinhas', 'portas',
  'preco_compra', 'arv_total', 'meses_carrego',
];
const CAMPOS_BOOLEANOS = [
  'eletrica_completa', 'hidraulica_completa_banheiro', 'hidraulica_completa_cozinha',
];

const state = { id: null, ultimaSimulacao: null, timer: null };

async function enviar(path, method, body) {
  const resposta = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({}));
    throw new Error(typeof erro.detail === 'string' ? erro.detail : `Erro ${resposta.status}`);
  }
  return resposta.status === 204 ? null : resposta.json();
}

function lerFormulario() {
  const dados = { endereco: $('f-endereco').value.trim() };
  const apelido = $('f-apelido').value.trim();
  const bairro = $('f-bairro').value.trim();
  if (apelido) dados.apelido = apelido;
  if (bairro) dados.bairro = bairro;
  CAMPOS_NUMERICOS.forEach((campo) => {
    const input = document.querySelector(`[name="${campo}"]`);
    dados[campo] = Number(input.value);
  });
  CAMPOS_BOOLEANOS.forEach((campo) => {
    dados[campo] = document.querySelector(`[name="${campo}"]`).checked;
  });
  dados.status = $('f-status').value;
  return dados;
}

function entradaDe(dados) {
  // O preview só quer a parte que entra na conta; endereço e apelido não entram.
  const entrada = {};
  [...CAMPOS_NUMERICOS, ...CAMPOS_BOOLEANOS]
    .filter((campo) => campo !== 'area_util_m2' && campo !== 'quartos')
    .forEach((campo) => { entrada[campo] = dados[campo]; });
  return entrada;
}

function mostrarErro(mensagem) {
  const caixa = $('erro');
  caixa.textContent = mensagem;
  caixa.hidden = !mensagem;
}

function linha(rotulo, valor, { total = false, negativa = false } = {}) {
  const div = el('div', `flip-linha${total ? ' flip-linha-total' : ''}${negativa ? ' flip-linha-negativa' : ''}`);
  div.appendChild(el('span', null, rotulo));
  div.appendChild(el('strong', 'flip-valor', valor));
  return div;
}

function pintarKpis(simulacao, areaUtil) {
  const { dre, orcamento } = simulacao;
  $('kpi-obra').textContent = formatCurrency(orcamento.total);
  $('kpi-obra-meta').textContent = areaUtil > 0
    ? `${formatCurrency(orcamento.total / areaUtil)} por m² de área útil`
    : '';
  $('kpi-capital').textContent = formatCurrency(dre.capital_empatado);
  $('kpi-lucro').textContent = formatCurrency(dre.lucro_liquido);
  $('kpi-lucro').classList.toggle('alta', dre.lucro_liquido >= 0);
  $('kpi-lucro-meta').textContent = `ROI de ${formatPct(dre.roi * 100)} sobre o capital`;
  $('kpi-tir').textContent = formatPct(dre.tir_anual * 100);
  $('kpi-tir-meta').textContent = `Margem de ${formatPct((dre.lucro_liquido / dre.venda) * 100)} sobre a venda`;
}

function pintarMao(simulacao, precoCompra) {
  $('mao-valor').textContent = formatCurrency(simulacao.mao);
  const folga = simulacao.mao - precoCompra;
  $('mao-comparativo').textContent = folga >= 0
    ? `Sua proposta de ${formatCurrency(precoCompra)} está ${formatCurrency(folga)} abaixo do teto.`
    : `Sua proposta de ${formatCurrency(precoCompra)} está ${formatCurrency(-folga)} acima do teto.`;
}

function pintarOrcamento(orcamento) {
  const alvo = $('orcamento');
  alvo.textContent = '';
  orcamento.grupos
    .filter((grupo) => grupo.itens.length)
    .forEach((grupo) => {
      const bloco = el('details', 'flip-grupo');
      const resumo = el('summary');
      resumo.appendChild(el('span', null, grupo.rotulo));
      resumo.appendChild(el('span', 'flip-valor', formatCurrency(grupo.total)));
      bloco.appendChild(resumo);
      grupo.itens.forEach((item) => {
        const linhaItem = el('div', 'flip-item');
        const quantidade = Number.isInteger(item.quantidade)
          ? item.quantidade
          : item.quantidade.toFixed(1);
        linhaItem.appendChild(el('span', null, `${item.rotulo} — ${quantidade} × ${formatCurrency(item.custo_unitario)}`));
        linhaItem.appendChild(el('span', 'flip-valor', formatCurrency(item.total)));
        bloco.appendChild(linhaItem);
      });
      alvo.appendChild(bloco);
    });
  alvo.appendChild(linha('Subtotal da obra', formatCurrency(orcamento.subtotal)));
  alvo.appendChild(linha('Contingência', formatCurrency(orcamento.contingencia)));
  alvo.appendChild(linha('Total da obra', formatCurrency(orcamento.total), { total: true }));
}

function pintarDre(dre) {
  const alvo = $('dre');
  alvo.textContent = '';
  alvo.appendChild(linha('(+) Venda estimada', formatCurrency(dre.venda)));
  alvo.appendChild(linha('(−) Corretagem', formatCurrency(dre.corretagem), { negativa: true }));
  alvo.appendChild(linha('(−) IR sobre ganho de capital', formatCurrency(dre.ir_ganho_capital), { negativa: true }));
  alvo.appendChild(linha('(−) Compra', formatCurrency(dre.preco_compra), { negativa: true }));
  alvo.appendChild(linha('(−) ITBI', formatCurrency(dre.itbi), { negativa: true }));
  alvo.appendChild(linha('(−) Escritura e registro', formatCurrency(dre.registro), { negativa: true }));
  alvo.appendChild(linha('(−) Obra', formatCurrency(dre.obra), { negativa: true }));
  alvo.appendChild(linha('(−) Carrego', formatCurrency(dre.carrego), { negativa: true }));
  alvo.appendChild(linha('(=) Lucro líquido', formatCurrency(dre.lucro_liquido), { total: true }));
}

function classeDaCelula(roi) {
  if (roi >= 0.18) return 'flip-celula-otima';
  if (roi >= 0.15) return 'flip-celula-aceitavel';
  return 'flip-celula-risco';
}

function pintarMatriz(matriz, mesesBase) {
  const alvo = $('matriz');
  alvo.textContent = '';
  const meses = [...new Set(matriz.map((c) => c.meses))].sort((a, b) => a - b);
  const variacoes = [...new Set(matriz.map((c) => c.variacao_venda))].sort((a, b) => b - a);

  const tabela = el('table', 'flip-matriz');
  const cabecalho = el('tr');
  cabecalho.appendChild(el('th', null, 'Venda \\ prazo'));
  meses.forEach((m) => cabecalho.appendChild(el('th', null, `${m} meses`)));
  tabela.appendChild(cabecalho);

  variacoes.forEach((variacao) => {
    const tr = el('tr');
    const rotulo = variacao === 0 ? 'Base' : formatPct(variacao * 100);
    tr.appendChild(el('th', null, rotulo));
    meses.forEach((m) => {
      const celula = matriz.find((c) => c.variacao_venda === variacao && c.meses === m);
      const td = el('td', classeDaCelula(celula.roi));
      if (variacao === 0 && m === mesesBase) td.classList.add('flip-celula-base');
      td.appendChild(el('span', null, formatPct(celula.roi * 100)));
      td.appendChild(el('span', 'flip-celula-lucro', formatCurrency(celula.lucro_liquido)));
      tr.appendChild(td);
    });
    tabela.appendChild(tr);
  });
  alvo.appendChild(tabela);
  alvo.appendChild(el('p', 'card-meta', 'Verde: ROI ≥ 18%. Cinza: entre 15% e 18%. Coral: abaixo de 15%.'));
}

function pintar(simulacao, dados) {
  state.ultimaSimulacao = simulacao;
  pintarKpis(simulacao, dados.area_util_m2);
  pintarMao(simulacao, dados.preco_compra);
  pintarOrcamento(simulacao.orcamento);
  pintarDre(simulacao.dre);
  pintarMatriz(simulacao.matriz, dados.meses_carrego);
}

async function calcular() {
  const dados = lerFormulario();
  if (!(dados.area_seca_m2 > 0) || !(dados.preco_compra > 0) || !(dados.arv_total > 0)) {
    mostrarErro('Área seca, preço de compra e valor de venda precisam ser maiores que zero.');
    return;
  }
  try {
    const simulacao = await enviar('/flips/preview', 'POST', entradaDe(dados));
    mostrarErro('');
    pintar(simulacao, dados);
  } catch (erro) {
    // Mantém os últimos números na tela: zerar tudo esconde o que o dono
    // estava olhando por causa de uma digitação a meio caminho.
    mostrarErro(`Não foi possível recalcular: ${erro.message}`);
  }
}

function agendarCalculo() {
  clearTimeout(state.timer);
  state.timer = setTimeout(calcular, 200);
}

async function referenciaDoBairro() {
  const bairro = $('f-bairro').value.trim();
  const alvo = $('ref-bairro');
  alvo.textContent = '';
  if (!bairro) return;
  try {
    const dados = await fetchJson(`/neighborhoods/${encodeURIComponent(bairro)}`, { months: 12 });
    if (dados && dados.median_price_m2) {
      alvo.textContent = `Mediana do bairro: ${formatCurrency(dados.median_price_m2)}/m² (ITBI, 12 meses).`;
    }
  } catch (erro) {
    // Referência é conforto, não requisito: sem ela a tela segue funcionando.
    alvo.textContent = '';
  }
}

function preencher(dados) {
  $('f-endereco').value = dados.endereco || '';
  $('f-apelido').value = dados.apelido || '';
  $('f-bairro').value = dados.bairro || '';
  CAMPOS_NUMERICOS.forEach((campo) => {
    const input = document.querySelector(`[name="${campo}"]`);
    if (dados[campo] !== null && dados[campo] !== undefined) input.value = dados[campo];
  });
  CAMPOS_BOOLEANOS.forEach((campo) => {
    document.querySelector(`[name="${campo}"]`).checked = Boolean(dados[campo]);
  });
  if (dados.status) $('f-status').value = dados.status;
}

async function carregarEstudo(id) {
  const estudo = await enviar(`/flips/${id}`, 'GET');
  state.id = estudo.id;
  preencher(estudo);
  $('btn-salvar').textContent = 'Salvar alterações';
}

async function salvar(evento) {
  evento.preventDefault();
  const dados = lerFormulario();
  if (!dados.endereco) {
    mostrarErro('O endereço identifica o estudo na lista; preencha antes de salvar.');
    return;
  }
  try {
    if (state.id) {
      await enviar(`/flips/${state.id}`, 'PATCH', dados);
    } else {
      const criado = await enviar('/flips', 'POST', { ...dados, origem: state.origem || 'manual', origem_id: state.origemId || null });
      state.id = criado.id;
      $('btn-salvar').textContent = 'Salvar alterações';
      window.history.replaceState({}, '', `/flip?id=${criado.id}`);
    }
    mostrarErro('');
  } catch (erro) {
    mostrarErro(`Não foi possível salvar: ${erro.message}`);
  }
}

async function iniciar() {
  await mountChrome('flip');
  const form = $('form-imovel');
  form.addEventListener('input', agendarCalculo);
  form.addEventListener('submit', salvar);
  $('f-bairro').addEventListener('change', referenciaDoBairro);
  $('btn-resetar').addEventListener('click', () => {
    form.reset();
    state.id = null;
    $('btn-salvar').textContent = 'Salvar estudo';
    window.history.replaceState({}, '', '/flip');
    calcular();
  });

  const params = new URLSearchParams(window.location.search);
  if (params.get('id')) {
    try {
      await carregarEstudo(params.get('id'));
    } catch (erro) {
      mostrarErro(`Estudo não encontrado: ${erro.message}`);
    }
  }
  await referenciaDoBairro();
  await calcular();
}

iniciar();
```

- [ ] **Step 2: Conferir o formato da referência de bairro**

Run: `.venv/bin/python -c "import json;from app.schemas.stats import NeighborhoodDetailOut;print(list(NeighborhoodDetailOut.model_fields))"`
Expected: a lista de campos. Se o campo de mediana por m² **não** se chamar `median_price_m2`, ajuste o nome dentro de `referenciaDoBairro` para o que o schema realmente expõe, e confira a rota certa em `app/api/routes/stats.py:145`.

- [ ] **Step 3: Verificar na mão**

Run: `.venv/bin/uvicorn app.main:app --reload --port 8000` e abra `http://localhost:8000/flip`.
Expected:
- KPIs preenchidos ao abrir (obra R$ 41.572,50 com os valores padrão da tela)
- mexer no preço de compra repinta tudo depois de ~200ms
- marcar os três toggles leva a obra para R$ 55.372,50
- a célula central da matriz aparece contornada e bate com o ROI do KPI
- "Salvar estudo" cria a linha e a URL passa a ter `?id=`

- [ ] **Step 4: Commit**

```bash
git add app/static/flip.js
git commit -m "feat: tela do simulador de flip com preview em tempo real"
```

---

### Task 11: Pipeline dos estudos (`flip-estudos.js`)

**Files:**
- Create: `app/static/flip-estudos.js`
- Test: verificação manual — passo 2 abaixo

**Interfaces:**
- Consumes: `window.IR`; `GET /flips` com filtros, `DELETE /flips/{id}`.
- Produces: a tela do pipeline.

- [ ] **Step 1: Escrever `app/static/flip-estudos.js`**

```javascript
/* Pipeline de estudos de flip.
 *
 * Cada linha vem com os indicadores já recalculados pelo servidor, com as
 * premissas que aquele estudo congelou. A tela ordena e filtra, nada mais.
 */
const { API_BASE, $, el, emptyState, fetchJson, formatCurrency, formatPct, mountChrome, navigate } = window.IR;

const ROTULO_STATUS = {
  oportunidade: 'Oportunidade',
  em_analise: 'Em análise',
  descartado: 'Descartado',
};

const state = { estudos: [] };

function mostrarErro(mensagem) {
  const caixa = $('erro');
  caixa.textContent = mensagem;
  caixa.hidden = !mensagem;
}

function filtros() {
  return {
    bairro: $('f-bairro').value.trim(),
    status: $('f-status').value,
    preco_min: $('f-preco-min').value,
    preco_max: $('f-preco-max').value,
  };
}

function pintarKpis(estudos) {
  const alvo = $('kpis');
  alvo.textContent = '';
  const ativos = estudos.filter((e) => e.status !== 'descartado');
  const capital = ativos.reduce((soma, e) => soma + e.capital_empatado, 0);
  const lucro = ativos.reduce((soma, e) => soma + e.lucro_liquido, 0);
  const tirMedia = ativos.length
    ? ativos.reduce((soma, e) => soma + e.tir_anual, 0) / ativos.length
    : 0;

  const cartao = (rotulo, valor, meta) => {
    const card = el('article', 'card');
    card.appendChild(el('span', 'card-label', rotulo));
    card.appendChild(el('strong', 'card-value', valor));
    if (meta) card.appendChild(el('span', 'card-meta', meta));
    return card;
  };

  alvo.appendChild(cartao('Estudos ativos', String(ativos.length), `${estudos.length} no total`));
  alvo.appendChild(cartao('Capital comprometido', formatCurrency(capital), 'Se todas as compras fecharem'));
  alvo.appendChild(cartao('Lucro projetado', formatCurrency(lucro), 'Soma dos estudos ativos'));
  alvo.appendChild(cartao('TIR média', formatPct(tirMedia * 100), 'Média simples, não ponderada'));
}

function celulaNumerica(texto, classe) {
  const td = el('td', classe ? `num ${classe}` : 'num', texto);
  return td;
}

function pintarTabela(estudos) {
  const corpo = $('corpo-tabela');
  corpo.textContent = '';
  $('vazio').textContent = '';
  $('tabela').hidden = estudos.length === 0;

  if (!estudos.length) {
    $('vazio').appendChild(
      emptyState(
        'Nenhum estudo salvo ainda',
        'Simule um imóvel e clique em "Salvar estudo" para ele aparecer aqui.',
        [{ label: 'Abrir o simulador', href: '/flip' }],
      ),
    );
    return;
  }

  estudos.forEach((estudo) => {
    const tr = el('tr');
    const identidade = el('td');
    identidade.appendChild(el('strong', null, estudo.apelido || estudo.endereco));
    if (estudo.apelido) identidade.appendChild(el('span', 'card-meta', estudo.endereco));
    tr.appendChild(identidade);
    tr.appendChild(el('td', null, estudo.bairro || '—'));
    tr.appendChild(celulaNumerica(formatCurrency(estudo.preco_compra)));
    tr.appendChild(celulaNumerica(formatCurrency(estudo.obra_total)));
    tr.appendChild(celulaNumerica(formatCurrency(estudo.capital_empatado)));
    tr.appendChild(celulaNumerica(formatCurrency(estudo.lucro_liquido), estudo.lucro_liquido >= 0 ? 'alta' : 'baixa'));
    tr.appendChild(celulaNumerica(formatPct(estudo.roi * 100)));
    tr.appendChild(celulaNumerica(formatPct(estudo.tir_anual * 100)));
    // Teto acima da proposta é margem; abaixo, é alerta.
    tr.appendChild(celulaNumerica(formatCurrency(estudo.mao), estudo.mao >= estudo.preco_compra ? 'alta' : 'baixa'));
    tr.appendChild(el('td', null, ROTULO_STATUS[estudo.status] || estudo.status));

    const acoes = el('td');
    const abrir = el('button', 'btn btn-secondary btn-sm', 'Abrir');
    abrir.addEventListener('click', (evento) => navigate(evento, `/flip?id=${estudo.id}`));
    const excluir = el('button', 'btn btn-ghost btn-sm', 'Excluir');
    excluir.addEventListener('click', async () => {
      if (!window.confirm(`Excluir o estudo de ${estudo.apelido || estudo.endereco}?`)) return;
      const resposta = await fetch(`${API_BASE}/flips/${estudo.id}`, { method: 'DELETE' });
      if (!resposta.ok) {
        mostrarErro(`Não foi possível excluir: erro ${resposta.status}`);
        return;
      }
      await carregar();
    });
    acoes.append(abrir, excluir);
    tr.appendChild(acoes);
    corpo.appendChild(tr);
  });
}

async function carregar() {
  try {
    state.estudos = await fetchJson('/flips', filtros());
    mostrarErro('');
  } catch (erro) {
    mostrarErro(`Não foi possível carregar os estudos: ${erro.message}`);
    return;
  }
  pintarKpis(state.estudos);
  pintarTabela(state.estudos);
}

async function iniciar() {
  await mountChrome('flip');
  $('filtros').addEventListener('submit', (evento) => evento.preventDefault());
  ['f-bairro', 'f-status', 'f-preco-min', 'f-preco-max'].forEach((id) => {
    $(id).addEventListener('change', carregar);
  });
  await carregar();
}

iniciar();
```

- [ ] **Step 2: Verificar na mão**

Com o servidor rodando, abra `http://localhost:8000/flip/estudos`.
Expected: lista vazia mostra o estado vazio com botão para o simulador; depois de salvar dois estudos, os KPIs somam os dois, o filtro de bairro reduz a lista, "Abrir" volta ao simulador preenchido e "Excluir" pede confirmação.

- [ ] **Step 3: Commit**

```bash
git add app/static/flip-estudos.js
git commit -m "feat: pipeline de estudos de flip"
```

---

### Task 12: Ponte a partir de oportunidade e leilão

**Files:**
- Modify: `app/static/oportunidades.js`
- Modify: `app/static/leilao.js`
- Modify: `app/static/flip.js`
- Test: verificação manual — passo 4 abaixo

**Interfaces:**
- Consumes: `GET /opportunities/{id}` (campos `rua`, `numero`, `bairro`, `cidade`, `quartos`, `banheiros`, `area_util_m2`, `preco_anunciado`); `GET /auctions/{id}` — na prática `GET /auctions` e o item da lista — (campos `address`, `address_number`, `neighborhood`, `city`, `total_area`, `bedroom_count`, `bathroom_count`, `lance_minimo`).
- Produces: `state.origem` / `state.origemId` preenchidos em `flip.js`, gravados como `origem` / `origem_id` ao salvar.

- [ ] **Step 1: Acrescentar o pré-preenchimento em `app/static/flip.js`**

Dentro de `iniciar()`, logo antes do bloco `if (params.get('id'))`, insira:

```javascript
  const origem = params.get('origem');
  const origemId = params.get('origem_id');
  if (origem && origemId && !params.get('id')) {
    try {
      await preencherDaOrigem(origem, origemId);
      state.origem = origem;
      state.origemId = Number(origemId);
    } catch (erro) {
      mostrarErro(`Não foi possível trazer os dados de origem: ${erro.message}`);
    }
  }
```

E acrescente a função, acima de `iniciar`:

```javascript
/* O que a origem sabe entra; o que ela não sabe (área seca, portas) fica no
 * padrão da tela, para o dono corrigir olhando as fotos. */
async function preencherDaOrigem(origem, origemId) {
  if (origem === 'oportunidade') {
    const anuncio = await enviar(`/opportunities/${origemId}`, 'GET');
    const numero = anuncio.numero ? `, ${anuncio.numero}` : '';
    preencher({
      endereco: `${anuncio.rua || ''}${numero}`.trim(),
      bairro: anuncio.bairro || '',
      area_util_m2: anuncio.area_util_m2 || undefined,
      area_seca_m2: anuncio.area_util_m2 || undefined,
      quartos: anuncio.quartos ?? undefined,
      banheiros: anuncio.banheiros ?? undefined,
      preco_compra: anuncio.preco_anunciado || undefined,
    });
    return;
  }
  if (origem === 'leilao') {
    const imoveis = await enviar('/auctions?incluir_passados=true', 'GET');
    const imovel = imoveis.find((item) => String(item.id) === String(origemId));
    if (!imovel) throw new Error('imóvel de leilão não encontrado');
    const numero = imovel.address_number ? `, ${imovel.address_number}` : '';
    preencher({
      apelido: imovel.apelido || '',
      endereco: `${imovel.address || ''}${numero}`.trim(),
      bairro: imovel.neighborhood || '',
      area_util_m2: imovel.total_area || undefined,
      area_seca_m2: imovel.total_area || undefined,
      quartos: imovel.bedroom_count ?? undefined,
      banheiros: imovel.bathroom_count ?? undefined,
      preco_compra: imovel.lance_minimo || undefined,
    });
  }
}
```

- [ ] **Step 2: Botão em `app/static/oportunidades.js`**

Localize onde cada anúncio monta seus botões de ação (procure por `btn btn-secondary btn-sm` no arquivo) e acrescente, ao lado dos existentes:

```javascript
  const simular = el('a', 'btn btn-secondary btn-sm', 'Simular flip');
  simular.href = `/flip?origem=oportunidade&origem_id=${item.id}`;
  acoes.appendChild(simular);
```

Use o nome de variável que o arquivo já usa para o anúncio da vez e para o contêiner de ações — se forem outros, adapte; o conteúdo do link é o que importa.

- [ ] **Step 3: Botão em `app/static/leilao.js`**

No mesmo lugar onde a linha do imóvel monta suas ações, acrescente:

```javascript
  const simular = el('a', 'btn btn-secondary btn-sm', 'Simular flip');
  simular.href = `/flip?origem=leilao&origem_id=${imovel.id}`;
  acoes.appendChild(simular);
```

- [ ] **Step 4: Verificar na mão**

Com o servidor rodando:
- em `/oportunidades`, clicar em "Simular flip" abre `/flip` com endereço, bairro, área e preço do anúncio preenchidos
- salvar esse estudo e conferir em `/flip/estudos` que ele aparece; conferir via `GET /flips/{id}` que `origem` é `oportunidade` e `origem_id` casa com o anúncio
- o mesmo a partir de `/leilao`, com `origem` igual a `leilao`

- [ ] **Step 5: Rodar a suíte inteira**

Run: `.venv/bin/pytest`
Expected: tudo verde. Nada nas telas de origem quebrou — os arquivos só ganharam um link.

- [ ] **Step 6: Commit**

```bash
git add app/static/flip.js app/static/oportunidades.js app/static/leilao.js
git commit -m "feat: simular flip a partir de oportunidade e de leilão"
```
