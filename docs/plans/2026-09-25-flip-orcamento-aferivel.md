# Flip orçamento aferível Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Tornar o orçamento do `/flip` auditável por escopo, quantitativos e fonte, sem alterar estudos existentes.

**Architecture:** Preservar o motor legado para estudos antigos e introduzir o motor aferível por escopo. Salvar escopo e medições junto ao estudo; preços SUDECAP ficam versionados nas premissas e snapshots. Itens sem composição comparável continuam provisões explícitas.

**Tech Stack:** Python, FastAPI, Pydantic, SQLAlchemy, Alembic, JavaScript, pytest.

---

### Task 1: Contrato e persistência

**Files:** `app/schemas/flips.py`, `app/models/flip_study.py`, `app/api/routes/flips.py`, `app/services/flip_studies.py`, `alembic/versions/0028_flip_orcamento_aferivel.py`, `tests/test_api/test_flips.py`.

1. Escrever testes para preview e persistência de escopo/medições, inclusive legado.
2. Rodar `pytest tests/test_api/test_flips.py -q`; esperar falha.
3. Adicionar campos validados e migração com padrão `legado` para registros anteriores.
4. Rodar os testes; esperar aprovação.

### Task 2: Motor de custos

**Files:** `app/domain/flip.py`, `app/config/flip_premissas.json`, `tests/test_domain/test_flip.py`.

1. Escrever testes para escopos e quantidades: pintura, demolição/recomposição, elétrica e hidráulica sem dupla contagem.
2. Rodar `pytest tests/test_domain/test_flip.py -q`; esperar falha.
3. Adicionar itens SUDECAP 07/2026 somente quando unidade e abrangência forem comparáveis; manter provisões explícitas para demais serviços.
4. Rodar os testes; esperar aprovação.

### Task 3: Tela e documentação

**Files:** `app/static/flip.html`, `app/static/flip.js`, `docs/flip-sinapi-mg-2026-09.md`, `tests/test_api/test_pages.py`.

1. Expor seleção de escopo e medições opcionais, e fonte/limitação junto ao orçamento.
2. Rodar `pytest tests/test_api/test_pages.py -q`; esperar aprovação.
3. Documentar limites da tabela de referência e orientação para cotação real.
4. Rodar `pytest tests/test_domain/test_flip.py tests/test_api/test_flips.py tests/test_api/test_pages.py -q`; esperar aprovação.
