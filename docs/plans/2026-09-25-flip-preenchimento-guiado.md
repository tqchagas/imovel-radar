# Flip preenchimento guiado Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Permitir preencher todos os dados do `/flip` em um modal progressivo, sem perder o formulário manual nem os estudos salvos.

**Architecture:** O formulário existente continua como fonte única dos dados enviados à API. O modal usa controles temporários espelhados por campo, atualizando o formulário imediatamente; a navegação por etapas apenas organiza as perguntas, aplica validação local e exibe revisão antes de mostrar a simulação. O guia abre automaticamente em novos estudos e pode ser reaberto por botão; estudos salvos não são interrompidos.

**Tech Stack:** HTML dialog nativo, JavaScript, CSS, FastAPI page tests, pytest.

---

### Task 1: Contrato da tela

**Files:** `tests/test_api/test_pages.py`, `app/static/flip.html`.

1. Adicionar teste de página para CTA e `dialog` guiado.
2. Rodar `.venv/bin/pytest tests/test_api/test_pages.py -q`; esperar falha.
3. Adicionar estrutura sem duplicar os campos canônicos.
4. Rodar o teste; esperar aprovação.

### Task 2: Motor do guia

**Files:** `app/static/flip.js`.

1. Definir etapas: imóvel, escopo, acabamentos, infraestrutura, negócio, revisão.
2. Gerar perguntas a partir dos campos já existentes e espelhar cada edição imediatamente.
3. Esconder medições irrelevantes ao escopo, validar essenciais, permitir voltar, fechar e retomar sem perda.
4. Abrir automaticamente só em novo estudo, nunca ao editar `?id=`.
5. Rodar `node --check app/static/flip.js`; esperar aprovação.

### Task 3: Acessibilidade e verificação

**Files:** `app/static/styles.css`, `tests/test_api/test_pages.py`.

1. Estilizar modal responsivo, progresso, botões e mensagens de erro visíveis.
2. Verificar Escape, foco, fechamento pelo fundo e botão de reabertura.
3. Rodar `.venv/bin/pytest tests/test_api/test_pages.py -q` e `git diff --check`; esperar aprovação.
