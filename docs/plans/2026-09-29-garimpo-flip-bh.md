# Garimpo de oportunidades para flip em Belo Horizonte — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fazer o serviço do ImovelRadar encontrar diariamente anúncios residenciais convencionais em BH, validar anúncios individuais e classificar oportunidades por comparação com a mediana do QuintoAndar no mesmo bairro e faixa de área.

**Architecture:** Acrescentar uma consulta especializada sobre os snapshots ativos de Loft, QuintoAndar e VivaReal, mantendo a página geral de oportunidades intacta. O cálculo de garimpo usa exclusivamente anúncios QuintoAndar como comparáveis, mediana de R$/m² por bairro e faixa (30–60, 60–90, 90–130 e 130–350 m²), e só inclui candidatos com área, vaga, preço, página individual e amostra mínima confirmados. Um ciclo de coleta específico dos bairros alvo alimenta a tela diária.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Alembic, Typer, Docker Compose e JavaScript estático.

---

### Task 1: Criar regra de elegibilidade e mediana do garimpo

**Files:**
- Create: `app/domain/flip_opportunities.py`
- Create: `app/services/flip_opportunities.py`
- Modify: `app/models/market_comparable.py`
- Create: `alembic/versions/0029_flip_listing_verification.py`

Filtrar BH, bairros prioritários e complementares definidos pelo usuário, preço até R$ 700.000, residencial, pelo menos uma vaga, área publicada e página individual acessível. Excluir Rua Perimetral no Prado e sinalizadores textuais de leilão, Caixa/banco, adjudicação ou venda judicial. Deduplicar snapshots pela impressão digital da unidade. Calcular a mediana somente com anúncios ativos do QuintoAndar no mesmo bairro/faixa, excluindo a própria unidade; exigir no mínimo cinco comparáveis distintos. Aplicar os três status e ordenar pelo gap decrescente.

### Task 2: Expor API e tela do garimpo

**Files:**
- Create: `app/schemas/flip_opportunities.py`
- Modify: `app/api/routes/opportunities.py`
- Modify: `app/main.py`
- Create: `app/static/garimpo.html`
- Create: `app/static/garimpo.js`
- Modify: `app/static/common.js`

Adicionar endpoint e página `/garimpo` separados da classificação geral por ITBI. Exibir apenas linhas elegíveis e verificadas, com anúncio, campos confirmados, R$/m² do anúncio, R$/m² mediano do QuintoAndar, gap, status, tamanho da amostra e link individual.

### Task 3: Agendar coleta e validação em produção

**Files:**
- Modify: `app/ingestion/cli.py`
- Modify: `scheduler.sh`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `README.md`

Adicionar comando para varrer os bairros permitidos nas fontes já disponíveis, verificar páginas individuais por HTTP normal e recalcular os resultados. Bloqueios, CAPTCHA, erro HTTP, página genérica, anúncio inativo, área/vaga/preço ausentes ou referência sem amostra suficiente deixam o anúncio fora da lista; não contornar proteções dos portais. O scheduler recalcula sempre, mesmo sem configuração de e-mail, e fica configurado para os 15 bairros definidos.

### Task 4: Deploy e inicialização do ciclo real

Publicar a alteração, aplicar a migration, coletar o primeiro ciclo nos bairros definidos, ativar o serviço scheduler do Docker em produção e verificar saúde do serviço, totais por status e URLs retornadas pela API `/opportunities/flip`.

