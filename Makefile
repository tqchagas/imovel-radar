# ImovelRadar — atalhos para rodar o projeto na máquina local.
#
# Fluxo do zero:
#   make setup && make base ARQUIVO=~/Downloads/itbi.csv && make run
#
# Manutenção (repetir): make tudo
# Produção:             make deploy
#
# Variáveis podem ser sobrescritas na linha de comando:
#   make collect BAIRRO="Savassi" CIDADE="Belo Horizonte"

SHELL := /bin/bash

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
CLI := PYTHONPATH=. $(PY) -m app.ingestion.cli

COMPOSE := docker compose

# Parâmetros de coleta / cálculo.
CIDADE ?= Belo Horizonte
# A mesma cidade na forma como é gravada: minúscula, sem acento, sublinhado.
CIDADE_KEY ?= belo_horizonte
UF ?= MG
BAIRRO ?= Savassi
SOURCES ?= loft quintoandar vivareal
MAX_PAGES ?= 100
# Piso de ITBI por bairro para a varredura valer a pena; abaixo disso não há
# amostra para comparar contra.
MIN_VENDAS_BAIRRO ?= 30
FILTROS ?= {"tipo_imovel": "APARTAMENTO"}
NOTA_MINIMA ?= 80
# Estimativa do QuintoAndar (qpreço) como segunda referência da nota. O endpoint
# responde sem sessão, então não precisa de cookie. QPRECO=--sem-qpreco desliga.
QPRECO ?= --qpreco
QPRECO_LIMIT ?= 50
# Teto de páginas de condomínio por execução. São 19.117 prédios em BH e a
# coleta é dirigida pelo anúncio sem número, então ela converge em poucos ciclos.
CONDO_LIMIT ?= 500
# Contexto de vizinhança (endpoint de similares do QuintoAndar). Vale para as
# três fontes, não entra na nota. SIMILARES=--sem-similares desliga.
SIMILARES ?= --similares
SIMILARES_LIMIT ?= 50

# Servidor local.
HOST ?= 127.0.0.1
PORT ?= 8000

# Espera pelo Postgres.
DB_TIMEOUT ?= 60

# Deploy. O host precisa estar no ~/.ssh/config; veja docs/deploy-oracle-new.md.
DEPLOY_HOST ?= oracle-new
DEPLOY_PATH ?= ~/apps/imovel-radar
# Em produção todo comando precisa dos dois arquivos de compose. Sem o overlay,
# o compose republica a porta 8000 e colide com a outra stack do mesmo host.
DEPLOY_COMPOSE := export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml

# CSV de ITBI da prefeitura, para `make itbi`. Não há URL estável para baixar:
# o arquivo sai de dados.pbh.gov.br à mão.
ARQUIVO ?=

# Só para a mensagem final do `make tudo`: o valor que o domínio usa hoje.
AREA_FATOR_ATUAL := $(shell grep -E "^AREA_MATCH_FACTOR" app/domain/opportunities.py | cut -d= -f2 | tr -d " ")

SOURCE_FLAGS := $(foreach s,$(SOURCES),--source $(s))
# Um bairro por vez (nomes têm espaço). Vazio = cidade inteira no market-refresh.
BAIRRO_FLAGS := $(if $(strip $(BAIRRO)),--bairro "$(BAIRRO)",)

.DEFAULT_GOAL := help

## help: lista os alvos disponíveis
.PHONY: help
help:
	@echo "ImovelRadar — alvos disponíveis:"
	@echo
	@grep -E '^## ' $(MAKEFILE_LIST) \
		| sed -e 's/^## //' \
		| awk -F': ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Variáveis: CIDADE=$(CIDADE) UF=$(UF) BAIRRO=$(BAIRRO)"
	@echo "           SOURCES=$(SOURCES) MAX_PAGES=$(MAX_PAGES) NOTA_MINIMA=$(NOTA_MINIMA)"
	@echo "           MIN_VENDAS_BAIRRO=$(MIN_VENDAS_BAIRRO)"
	@echo "           HOST=$(HOST) PORT=$(PORT)"
	@echo "           QPRECO=$(QPRECO) QPRECO_LIMIT=$(QPRECO_LIMIT)"
	@echo "           SIMILARES=$(SIMILARES) SIMILARES_LIMIT=$(SIMILARES_LIMIT)"

## tudo: ciclo de manutenção — cadastro, varredura, condomínios, notas e aferição
.PHONY: tudo
tudo: db migrate
	@echo ""
	@echo "==> 1/6  Cadastro imobiliário da prefeitura: endereço, coordenada e"
	@echo "         padrão de acabamento por prédio. É o que faz o anúncio sem"
	@echo "         número de rua alcançar o tier de endereço. Mensal; barato repetir."
	-@$(MAKE) --no-print-directory cadastro
	@echo ""
	@echo "==> 2/6  Varrendo $(CIDADE) em $(SOURCES). Demora; os portais limitam a taxa."
	@# A varredura é best-effort: portal que recusa ou escopo truncado não pode
	@# impedir o recálculo, senão a base fica coletada e sem nota.
	-@$(MAKE) --no-print-directory sweep
	@echo ""
	@echo "==> 3/6  Diretório de condomínios: o número da rua que Loft e QuintoAndar"
	@echo "         não publicam. Depois da varredura, que é quem cria a demanda."
	-@$(MAKE) --no-print-directory condominios
	@echo ""
	@echo "==> 4/6  Recalculando notas e buscando qpreço e vizinhança."
	@$(MAKE) --no-print-directory score
	@echo ""
	@echo "==> 5/6  Registrando desfechos: anúncio que saiu do ar contra ITBI."
	@echo "         Não responde no mesmo dia — o ITBI atrasa dois meses."
	-@$(MAKE) --no-print-directory desfechos
	@echo ""
	@echo "==> 6/6  Aferindo o fator de área contra os pares do mesmo endereço."
	@PYTHONPATH=. $(PY) scripts/medir_area_itbi.py --cidade "$(CIDADE)"
	@echo ""
	@echo "     Pronto. Confira no JSON do passo 4:"
	@echo "    qpreco_interrompido / similares_interrompido devem ser null."
	@echo "    'bloqueado' significa que o portal recusou — pare antes de repetir."
	@echo "    Cada execução busca no máximo $(QPRECO_LIMIT) qpreços e $(SIMILARES_LIMIT)"
	@echo "    vizinhanças; rode 'make score' de novo nos próximos dias para a fila andar."
	@echo "    Se a mediana do passo 6 sair longe de $(AREA_FATOR_ATUAL), ajuste"
	@echo "    AREA_MATCH_FACTOR em app/domain/opportunities.py e rode 'make score'."

## setup: cria a venv, instala dependências e o .env
.PHONY: setup
setup: $(VENV)/bin/activate .env
	@echo "Pronto. Ative com: source $(VENV)/bin/activate"

$(VENV)/bin/activate: requirements.txt requirements-dev.txt
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt
	@touch $(VENV)/bin/activate

.env:
	cp .env.example .env
	@echo ".env criado a partir de .env.example — revise antes de coletar."

## db: sobe o Postgres e espera aceitar conexão
.PHONY: db
db: .env
	$(COMPOSE) up -d postgres
	@echo "Aguardando o Postgres aceitar conexão (timeout $(DB_TIMEOUT)s)..."
	@deadline=$$(( $$(date +%s) + $(DB_TIMEOUT) )); \
	until $(COMPOSE) exec -T postgres sh -c 'pg_isready -q -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"' 2>/dev/null; do \
		if [ $$(date +%s) -ge $$deadline ]; then \
			echo "Postgres não respondeu em $(DB_TIMEOUT)s. Veja: $(COMPOSE) logs postgres"; \
			exit 1; \
		fi; \
		sleep 1; \
	done
	@echo "Postgres pronto."

## migrate: aplica as migrations (alembic upgrade head)
.PHONY: migrate
migrate:
	PYTHONPATH=. $(ALEMBIC) upgrade head

## itbi: ingere o CSV de ITBI da prefeitura (ARQUIVO=caminho/para.csv)
.PHONY: itbi
itbi:
	@test -n "$(ARQUIVO)" || { \
		echo "Falta o arquivo. Baixe o CSV em dados.pbh.gov.br e rode:"; \
		echo "  make itbi ARQUIVO=~/Downloads/itbi.csv"; exit 1; }
	@test -f "$(ARQUIVO)" || { echo "Arquivo não encontrado: $(ARQUIVO)"; exit 1; }
	$(CLI) ingest --city "$(CIDADE_KEY)" --file "$(ARQUIVO)"

## base: do zero até ter tudo no banco (ITBI, cadastro, condomínios, anúncios, notas)
.PHONY: base
base: db migrate
	@echo ""
	@echo "==> 1/6  ITBI da prefeitura. É a fundação: sem ele não há referência de"
	@echo "         preço, e nada mais nesta lista tem contra o que comparar."
	@if [ -n "$(ARQUIVO)" ]; then \
		$(MAKE) --no-print-directory itbi; \
	else \
		echo "         (pulado: rode com ARQUIVO=... para ingerir, ou use /enviar)"; \
	fi
	@echo ""
	@echo "==> 2/6  Cadastro imobiliário: endereço, coordenada e área por unidade."
	@echo "         Mensal, e vem antes de tudo porque é o que dá coordenada ao resto."
	-@$(MAKE) --no-print-directory cadastro
	@echo ""
	@echo "==> 3/6  Anúncios de $(CIDADE) em $(SOURCES). Demora; os portais limitam a taxa."
	-@$(MAKE) --no-print-directory sweep
	@echo ""
	@echo "==> 4/6  Diretório de condomínios: o número da rua que Loft e QuintoAndar"
	@echo "         não publicam. Vem depois da varredura, que é quem cria a demanda."
	@echo "         São 19.117 prédios em BH e cada execução tem teto de $(CONDO_LIMIT);"
	@echo "         repita em ciclos seguintes para a cobertura crescer."
	-@$(MAKE) --no-print-directory condominios
	@echo ""
	@echo "==> 5/6  Notas, qpreço e contexto de vizinhança."
	@$(MAKE) --no-print-directory score
	@echo ""
	@echo "==> 6/6  Desfechos: anúncio que saiu do ar contra quitação de ITBI."
	-@$(MAKE) --no-print-directory desfechos
	@echo ""
	@echo "     Banco pronto. 'make run' sobe a API; 'make validar' mede o erro."

## collect: coleta um bairro nas fontes configuradas
.PHONY: collect
collect:
	$(CLI) market-refresh \
		--cidade "$(CIDADE)" --uf "$(UF)" $(BAIRRO_FLAGS) $(SOURCE_FLAGS) \
		--filtros '$(FILTROS)' --max-pages $(MAX_PAGES)

## sweep: varre a cidade inteira, bairro a bairro (demorado)
.PHONY: sweep
sweep:
	$(CLI) market-sweep \
		--cidade "$(CIDADE)" --uf "$(UF)" $(SOURCE_FLAGS) \
		--filtros '$(FILTROS)' --max-pages $(MAX_PAGES) \
		--min-vendas-bairro $(MIN_VENDAS_BAIRRO)

## cadastro: baixa o cadastro imobiliário da prefeitura (endereço + coordenada)
.PHONY: cadastro
cadastro:
	$(CLI) registry-sync --cidade "$(CIDADE_KEY)"

## condominios: baixa as páginas de condomínio dos bairros com anúncio sem número
.PHONY: condominios
condominios:
	$(CLI) condo-sync --cidade "$(CIDADE_KEY)" --limit $(CONDO_LIMIT)

## ipca: baixa a série do IPCA no Banco Central (corrige os valores para hoje)
.PHONY: ipca
ipca:
	$(CLI) ipca

## leilao: reavalia um imóvel de leilão (a tela /leilao faz o mesmo num clique)
.PHONY: leilao
leilao:
	$(CLI) avaliar-leilao --id $(ID) $(if $(FORCE),--force,)

## desfechos: registra saídas de anúncio e procura a quitação de ITBI de cada uma
.PHONY: desfechos
desfechos:
	$(CLI) outcome-track --cidade "$(CIDADE_KEY)"

## validar: erro medido da escada de referência e da calibração
.PHONY: validar
validar:
	@PYTHONPATH=. $(PY) scripts/validar_referencia.py --cidade "$(CIDADE_KEY)"
	@echo ""
	@PYTHONPATH=. $(PY) scripts/validar_calibracao.py --cidade "$(CIDADE_KEY)"

## score: recalcula as notas e descontos das oportunidades
.PHONY: score
score:
	$(CLI) opportunity-refresh --cidade "$(CIDADE)" --nota-minima $(NOTA_MINIMA) \
		$(QPRECO) --qpreco-limit $(QPRECO_LIMIT) \
		$(SIMILARES) --similares-limit $(SIMILARES_LIMIT)

## alerts: recalcula e envia os e-mails de alerta (precisa de SMTP + config)
.PHONY: alerts
alerts:
	$(CLI) opportunity-alerts \
		--cidade "$(CIDADE)" --uf "$(UF)" $(SOURCE_FLAGS) --skip-refresh \
		$(QPRECO) --qpreco-limit $(QPRECO_LIMIT)

## run: sobe a API em http://HOST:PORT/oportunidades
.PHONY: run
run:
	@echo "API em http://$(HOST):$(PORT)/oportunidades"
	$(UVICORN) app.main:app --reload --host $(HOST) --port $(PORT)

## test: roda a suíte de testes
.PHONY: test
test:
	$(VENV)/bin/pytest

## up: sobe a stack inteira no Docker (web + postgres)
.PHONY: up
up: .env
	$(COMPOSE) up --build -d

## down: derruba os containers (mantém o volume de dados)
.PHONY: down
down:
	$(COMPOSE) down

## logs: acompanha os logs da stack Docker
.PHONY: logs
logs:
	$(COMPOSE) logs -f

# --- Produção ---------------------------------------------------------------
# Tudo aqui roda por SSH no host de produção. O CLI vive dentro do container
# `web`, então os comandos de dado passam por `docker compose exec`.

## deploy: git pull + rebuild no servidor (reinicia a produção)
.PHONY: deploy
deploy:
	@echo "Isto vai reiniciar a produção em $(DEPLOY_HOST):"
	@echo "  git pull && docker compose up -d --build"
	@git status --porcelain | grep -q . && echo "  ATENÇÃO: há mudanças locais sem commit — elas NÃO vão junto." || true
	@printf "Continuar? [s/N] "; read r; [ "$$r" = "s" ] || { echo "Cancelado."; exit 1; }
	ssh $(DEPLOY_HOST) 'cd $(DEPLOY_PATH) && git pull && $(DEPLOY_COMPOSE) && docker compose up -d --build'
	@echo ""
	@echo "As migrations rodam sozinhas no entrypoint. Acompanhe com 'make deploy-logs'."

## deploy-logs: acompanha os logs da web em produção
.PHONY: deploy-logs
deploy-logs:
	ssh -t $(DEPLOY_HOST) 'cd $(DEPLOY_PATH) && $(DEPLOY_COMPOSE) && docker compose logs -f --tail 100 web'

## deploy-ps: o que está de pé em produção
.PHONY: deploy-ps
deploy-ps:
	ssh $(DEPLOY_HOST) 'cd $(DEPLOY_PATH) && $(DEPLOY_COMPOSE) && docker compose ps'

## deploy-base: roda o ciclo de dados no servidor (cadastro, anúncios, condomínios, notas)
.PHONY: deploy-base
deploy-base:
	@echo "Isto vai rodar horas de coleta em $(DEPLOY_HOST). O ITBI não entra aqui:"
	@echo "ele é ingerido pela tela /enviar, porque o CSV não tem URL estável."
	@printf "Continuar? [s/N] "; read r; [ "$$r" = "s" ] || { echo "Cancelado."; exit 1; }
	ssh -t $(DEPLOY_HOST) 'cd $(DEPLOY_PATH) && $(DEPLOY_COMPOSE) && \
		docker compose exec -T web python -m app.ingestion.cli registry-sync --cidade "$(CIDADE_KEY)" && \
		docker compose exec -T web python -m app.ingestion.cli market-sweep --cidade "$(CIDADE)" --uf "$(UF)" --filtros '"'"'$(FILTROS)'"'"' --min-vendas-bairro $(MIN_VENDAS_BAIRRO) && \
		docker compose exec -T web python -m app.ingestion.cli condo-sync --cidade "$(CIDADE_KEY)" --limit $(CONDO_LIMIT) && \
		docker compose exec -T web python -m app.ingestion.cli opportunity-refresh --cidade "$(CIDADE)" --qpreco-limit $(QPRECO_LIMIT) --similares-limit $(SIMILARES_LIMIT) && \
		docker compose exec -T web python -m app.ingestion.cli outcome-track --cidade "$(CIDADE_KEY)"'

## deploy-scheduler: liga o container que roda o ciclo sozinho, todo dia
.PHONY: deploy-scheduler
deploy-scheduler:
	ssh $(DEPLOY_HOST) 'cd $(DEPLOY_PATH) && $(DEPLOY_COMPOSE) && docker compose --profile scheduler up -d scheduler'
	@echo "Ligado. Ajuste SWEEP_INTERVAL_SECONDS e CONDO_LIMIT no .env do servidor."

## deploy-psql: abre o psql do banco de produção
.PHONY: deploy-psql
deploy-psql:
	ssh -t $(DEPLOY_HOST) 'cd $(DEPLOY_PATH) && $(DEPLOY_COMPOSE) && docker compose exec postgres psql -U imovelradar -d imovelradar'

## clean: remove venv, caches e containers (preserva o .env)
.PHONY: clean
clean:
	$(COMPOSE) down
	rm -rf $(VENV) .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
