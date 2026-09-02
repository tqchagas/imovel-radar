# ImovelRadar — atalhos para rodar o projeto na máquina local.
#
# Fluxo do zero:
#   make setup && make db && make migrate && make collect && make score && make run
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
UF ?= MG
BAIRRO ?= Savassi
SOURCES ?= loft quintoandar vivareal
MAX_PAGES ?= 100
FILTROS ?= {"tipo_imovel": "APARTAMENTO"}
NOTA_MINIMA ?= 80
# Estimativa do QuintoAndar (qpreço) como segunda referência da nota. O endpoint
# responde sem sessão, então não precisa de cookie. QPRECO=--sem-qpreco desliga.
QPRECO ?= --qpreco
QPRECO_LIMIT ?= 50

# Servidor local.
HOST ?= 127.0.0.1
PORT ?= 8000

# Espera pelo Postgres.
DB_TIMEOUT ?= 60

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
	@echo "           HOST=$(HOST) PORT=$(PORT)"
	@echo "           QPRECO=$(QPRECO) QPRECO_LIMIT=$(QPRECO_LIMIT)"

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
		--filtros '$(FILTROS)' --max-pages $(MAX_PAGES)

## score: recalcula as notas e descontos das oportunidades
.PHONY: score
score:
	$(CLI) opportunity-refresh --cidade "$(CIDADE)" --nota-minima $(NOTA_MINIMA) \
		$(QPRECO) --qpreco-limit $(QPRECO_LIMIT)

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

## clean: remove venv, caches e containers (preserva o .env)
.PHONY: clean
clean:
	$(COMPOSE) down
	rm -rf $(VENV) .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
