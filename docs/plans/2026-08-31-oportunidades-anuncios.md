# Oportunidades de anúncios imobiliários Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Coletar anúncios de venda do QuintoAndar e VivaReal, estimar seu valor usando ITBI recente e disponibilizar oportunidades com desconto na API, tela e e-mail.

**Architecture:** Adaptar os coletores do `auction-monitor` para um contrato próprio do ImovelRadar. Persistir snapshots idempotentes em `market_comparables`, calcular oportunidades em um domínio isolado usando preço por m² ITBI e executar coleta/cálculo/notificação por CLI agendável. A API e a tela consumirão apenas oportunidades ativas; SEO e a timeline de escrituras permanecem separados.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, Pydantic, Typer, Jinja/static JavaScript, pytest, SMTP via biblioteca padrão.

---

### Task 1: Expandir o modelo de anúncios e criar configurações de alerta

**Files:**
- Create: `alembic/versions/0003_opportunity_alerts.py`
- Modify: `app/models/market_comparable.py`
- Create: `app/models/opportunity_alert.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_models/test_market_comparable.py`

**Step 1: Write the failing tests**

Testar que `MarketComparable` suporta URL, endereço normalizado, status/escopo de coleta, `first_seen_at`, `last_seen_at` e campos de oportunidade calculada. Testar que a configuração global armazena filtros, destinatários, periodicidade e `rule_version`, e que notificações guardam `pending/sent/failed`, fingerprint e `activation_event_id`.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models/test_market_comparable.py -v`

Expected: FAIL because the new model fields/tables do not exist.

**Step 3: Implement the migration and models**

Adicionar colunas e índices necessários, mantendo `(source, listing_id)` único. Criar tabelas para a configuração global, execuções de coleta e eventos de notificação. Usar constraints para estados permitidos e um índice/constraint que permita verificar concorrência por anúncio, regra e evento de ativação.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models/test_market_comparable.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add alembic/versions/0003_opportunity_alerts.py app/models/market_comparable.py app/models/opportunity_alert.py tests/conftest.py tests/test_models/test_market_comparable.py
git commit -m "feat: adiciona modelo de oportunidades"
```

### Task 2: Adaptar coletores do QuintoAndar e VivaReal

**Files:**
- Create: `app/market_collectors/__init__.py`
- Create: `app/market_collectors/types.py`
- Create: `app/market_collectors/quintoandar.py`
- Create: `app/market_collectors/vivareal.py`
- Create: `app/market_collectors/normalize.py`
- Modify: `.env.example`
- Test: `tests/test_collectors/test_quintoandar.py`
- Test: `tests/test_collectors/test_vivareal.py`

**Step 1: Write the failing tests**

Usar payloads fixos extraídos dos testes do `auction-monitor` para verificar paginação, preço de venda, área, endereço, coordenadas, tipo, `listing_id` e URL. Cobrir IDs repetidos, anúncio sem preço, preço de aluguel, JSON inválido, HTTP não-2xx e limite de páginas cheio sem total.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_collectors -v`

Expected: FAIL because the ImovelRadar collector package does not exist.

**Step 3: Implement the common collector contract**

Criar `MarketQuery`, `NormalizedListing` e resultado de coleta com `success/partial`, `scope_key`, páginas e erro. Portar somente a lógica necessária de `market_collectors.py` do `auction-monitor`, sem importar o projeto externo em runtime. Implementar headers, URLs e configurações por ambiente; não persistir contatos sensíveis se não forem necessários para o alerta.

**Step 4: Implement deterministic pagination and normalization**

Encerrar em página vazia ou total informado. Usar limite padrão de 100; se a última página estiver cheia e não houver total, marcar parcial. IDs repetidos são ignorados. HTTP não-2xx, JSON inválido e estrutura inválida são fatais. Mapear tipos para `APARTAMENTO`/`CASA` e preservar endereço de rua/número quando disponível.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_collectors -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add app/market_collectors .env.example tests/test_collectors
git commit -m "feat: coleta anuncios de quintoandar e vivareal"
```

### Task 3: Persistir snapshots com escopo e falha segura

**Files:**
- Create: `app/services/market_refresh.py`
- Modify: `app/ingestion/cli.py`
- Test: `tests/test_services/test_market_refresh.py`

**Step 1: Write the failing tests**

Testar upsert idempotente, preservação de `first_seen_at`, atualização de `last_seen_at`, normalização de endereço, registro do `scope_key`, reativação e desativação apenas no mesmo escopo. Testar que erro de uma fonte ou coleta parcial não inativa anúncios.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services/test_market_refresh.py -v`

Expected: FAIL because refresh and scope tracking are not implemented.

**Step 3: Implement refresh**

Criar `canonical_scope_key` com JSON ordenado contendo fonte, UF, cidade, bairros ordenados e filtros. Fazer upsert por `(source, listing_id)`, associando o anúncio ao último escopo válido. Só executar desativação quando a coleta terminar com sucesso; escopo vazio de bairros representa todos os bairros da cidade e nunca deve conflitar com escopo específico.

**Step 4: Add the CLI command**

Adicionar `market-refresh` ao Typer, com fonte/cidade/bairros/filtros, limite de páginas e opção de não desativar. Emitir resumo por fonte e status parcial.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_services/test_market_refresh.py -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add app/services/market_refresh.py app/ingestion/cli.py tests/test_services/test_market_refresh.py
git commit -m "feat: persiste snapshots de anuncios"
```

### Task 4: Implementar cálculo de oportunidades

**Files:**
- Create: `app/domain/opportunities.py`
- Create: `app/services/opportunities.py`
- Create: `app/schemas/opportunities.py`
- Test: `tests/test_domain/test_opportunities.py`
- Test: `tests/test_services/test_opportunities.py`

**Step 1: Write the failing tests**

Cobrir `reference_date` na maior `settlement_date` residencial válida, janela inclusiva de 24 meses, valor por m², mediana, arredondamento, exclusão de valores/áreas inválidos, mapeamento de tipos, faixa +/-30%, thresholds 5/15, fallback `bairro_amplo`, desconto e confiança.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_domain/test_opportunities.py tests/test_services/test_opportunities.py -v`

Expected: FAIL because the opportunity calculator does not exist.

**Step 3: Implement pure calculation functions**

Implementar funções puras para selecionar comparáveis em ordem exata, bairro+tipo+área e bairro amplo; calcular `mediana(declared_value / built_area_acquired) * area_util_m2`; classificar alta/média/baixa; e gerar motivos legíveis. Usar os mapeamentos da especificação e nunca misturar comercial, vaga ou fração.

**Step 4: Implement persistence/query service**

Consultar anúncios ativos e ITBIs da cidade, materializar os campos calculados com `tipo_referencia`, amostra, datas, fingerprint e motivo. Não materializar baixa confiança como alerta enviável.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_domain/test_opportunities.py tests/test_services/test_opportunities.py -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add app/domain/opportunities.py app/services/opportunities.py app/schemas/opportunities.py tests/test_domain/test_opportunities.py tests/test_services/test_opportunities.py
git commit -m "feat: calcula oportunidades por desconto"
```

### Task 5: Expor API e tela de oportunidades

**Files:**
- Create: `app/api/routes/opportunities.py`
- Modify: `app/main.py`
- Create: `app/static/oportunidades.html`
- Create: `app/static/oportunidades.js`
- Modify: `app/templates/base.html`
- Test: `tests/test_api/test_opportunities.py`
- Modify: `tests/test_api/test_pages.py`

**Step 1: Write the failing tests**

Testar `GET /opportunities` com filtros de cidade, bairro, fonte, tipo, confiança, desconto, paginação e ordenação estável por desconto, preço e ID. Testar detalhe por ID, ausência de anúncios inativos e a rota `/oportunidades`.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api/test_opportunities.py tests/test_api/test_pages.py -v`

Expected: FAIL because the route and static page do not exist.

**Step 3: Implement API schemas and routes**

Adicionar resposta com preço anunciado/estimado, desconto em percentual/reais, confiança, tipo de referência, amostra, período ITBI, motivos e URL original. Manter a rota fora de SEO/sitemap e não alterar endpoints existentes de escrituras.

**Step 4: Implement the responsive page**

Adicionar a página com filtros, resumo, ranking e detalhe. Mostrar baixa confiança somente com aviso. Usar as ações de marcar vista/silenciar como estado local ou endpoint explicitamente modelado, sem misturar com timeline ITBI.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api/test_opportunities.py tests/test_api/test_pages.py -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add app/api/routes/opportunities.py app/main.py app/static/oportunidades.html app/static/oportunidades.js app/templates/base.html tests/test_api/test_opportunities.py tests/test_api/test_pages.py
git commit -m "feat: adiciona tela de oportunidades"
```

### Task 6: Implementar e-mail deduplicado

**Files:**
- Create: `app/notifications/email.py`
- Create: `app/services/opportunity_notifications.py`
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Test: `tests/test_notifications/test_opportunity_email.py`

**Step 1: Write the failing tests**

Testar primeira elegibilidade, confiança mínima, variação de preço de 3%, desconto de 5 pontos, estimativa de 5%, janela de 24 horas, múltiplos destinatários, estados `pending/sent/failed`, retry de falha e fingerprint estável.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notifications/test_opportunity_email.py -v`

Expected: FAIL because notification services do not exist.

**Step 3: Implement the email adapter**

Usar SMTP configurável por ambiente, com assunto e corpo contendo endereço, fonte, preços, desconto, confiança, amostra, datas e link. Falha de envio não deve alterar a linha de base `sent`.

**Step 4: Implement transactional deduplication**

Criar evento sob lock da configuração, revalidar o último envio em 24 horas e persistir `pending` antes do envio. Marcar `sent` somente após sucesso; `failed` e `pending` abandonado há mais de uma hora podem ser tentados novamente. `activation_event_id` permite novo alerta após retorno de anúncio inativo. Alteração de `rule_version` cria linha de base sem disparo em massa.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_notifications/test_opportunity_email.py -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add app/notifications app/services/opportunity_notifications.py app/core/config.py .env.example tests/test_notifications
git commit -m "feat: envia alertas de oportunidades"
```

### Task 7: Orquestrar job, documentação e verificação final

**Files:**
- Modify: `app/ingestion/cli.py`
- Modify: `README.md`
- Modify: `tests/test_health.py` or create `tests/test_integration/test_opportunity_flow.py`
- Modify: `.gitignore` if needed for local companion artifacts

**Step 1: Write the failing integration test**

Montar banco de teste com ITBIs e payloads de ambas as fontes; executar coleta, cálculo e notificação; verificar que uma fonte parcial preserva seus anúncios, a outra continua processando e apenas oportunidades elegíveis são enviadas.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration/test_opportunity_flow.py -v`

Expected: FAIL until the orchestration command is wired.

**Step 3: Implement the orchestration command**

Adicionar `opportunity-alerts` ao CLI para executar refresh, cálculo e e-mail em sequência, com logs por fonte e modo dry-run. Usar `America/Sao_Paulo` na configuração do agendamento e nunca fazer desativação quando houver coleta parcial.

**Step 4: Document operation**

Documentar variáveis SMTP, URLs/headers dos portais, comando de coleta, comando de alerta, migração, periodicidade sugerida e limitações. Explicitar que anúncios e oportunidades não entram nas páginas SEO.

**Step 5: Run the full verification suite**

Run: `pytest -v`

Expected: PASS for the full suite, including existing ITBI, SEO and API tests.

**Step 6: Review final diff and commit**

Run: `git status --short && git diff --check && git diff HEAD~1`

```bash
git add app/ingestion/cli.py README.md tests/test_integration/test_opportunity_flow.py .gitignore
git commit -m "feat: orquestra alertas de oportunidades"
```
