# Pergunta de Marcenaria no Flip Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Permitir que o usuário de `/flip` inclua ou retire a marcenaria de cozinha e banheiros do orçamento, preservando a escolha nos estudos salvos.

**Architecture:** Um booleano `incluir_marcenaria`, verdadeiro por padrão para manter o comportamento atual, atravessa a tela, os schemas da API, o domínio e a persistência. O orçamento usa esse campo somente para zerar os dois itens de marcenaria já existentes; as premissas de preço continuam sendo a fonte única dos valores.

**Tech Stack:** HTML e JavaScript sem framework, FastAPI/Pydantic, SQLAlchemy/Alembic e pytest.

---

### Task 1: Tornar a marcenaria opcional no orçamento

**Files:**
- Modify: `tests/test_domain/test_flip.py`
- Modify: `app/domain/flip.py`

**Step 1: Write the failing test**

Adicionar um teste que constrói `Imovel(..., incluir_marcenaria=False)` e comprova que `banho_marcenaria` e `coz_marcenaria` não aparecem, enquanto os demais itens continuam no orçamento.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -q`
Expected: FAIL porque `Imovel` ainda não aceita `incluir_marcenaria`.

**Step 3: Write minimal implementation**

Adicionar `incluir_marcenaria: bool = True` a `Imovel` e usar quantidade zero nos itens `banho_marcenaria` e `coz_marcenaria` quando a opção estiver desligada.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py -q`
Expected: PASS.

### Task 2: Levar e persistir a escolha pela API

**Files:**
- Create: `alembic/versions/0027_flip_study_carpentry.py`
- Modify: `app/models/flip_study.py`
- Modify: `app/schemas/flips.py`
- Modify: `app/api/routes/flips.py`
- Modify: `app/services/flip_studies.py`
- Modify: `tests/test_api/test_flips.py`

**Step 1: Write the failing tests**

Testar que o preview sem marcenaria reduz a obra em R$ 5.290,00 com contingência e que criar/consultar/editar um estudo mantém `incluir_marcenaria`.

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_api/test_flips.py -q`
Expected: FAIL porque o campo ainda é ignorado/ausente.

**Step 3: Write minimal implementation**

Adicionar o campo com padrão verdadeiro aos schemas, modelo e conversores; criar a migração com `server_default=true` para estudos existentes.

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_api/test_flips.py tests/test_models/test_flip_study.py -q`
Expected: PASS.

### Task 3: Expor a pergunta em `/flip`

**Files:**
- Modify: `app/static/flip.html`
- Modify: `app/static/flip.js`
- Test: `tests/test_api/test_pages.py`

**Step 1: Write the failing test**

Verificar no HTML de `/flip` a existência do checkbox `incluir_marcenaria`, marcado por padrão e com texto explicativo.

**Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_api/test_pages.py -q`
Expected: FAIL porque o controle ainda não existe.

**Step 3: Write minimal implementation**

Adicionar a pergunta à seção de reforma e incluir o nome em `CAMPOS_BOOLEANOS`, aproveitando a leitura, preenchimento, reset e debounce existentes.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_api/test_pages.py -q`
Expected: PASS.

### Task 4: Verificação integrada

**Files:**
- Verify only

**Step 1: Run focused suite**

Run: `.venv/bin/pytest tests/test_domain/test_flip.py tests/test_api/test_flips.py tests/test_api/test_pages.py tests/test_models/test_flip_study.py -q`
Expected: PASS.

**Step 2: Inspect migration chain**

Run: `.venv/bin/alembic heads`
Expected: `0027 (head)`.
