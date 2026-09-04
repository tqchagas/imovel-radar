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

## tudo: ciclo completo — banco, migrations, varredura, notas e a aferição
.PHONY: tudo
tudo: db migrate
	@echo ""
	@echo "==> 1/5  Cadastro imobiliário da prefeitura: endereço, coordenada e"
	@echo "         padrão de acabamento por prédio. É o que faz o anúncio sem"
	@echo "         número de rua alcançar o tier de endereço. Mensal; barato repetir."
	-@$(MAKE) --no-print-directory cadastro
	@echo ""
	@echo "==> 2/5  Varrendo $(CIDADE) em $(SOURCES). Demora; os portais limitam a taxa."
	@# A varredura é best-effort: portal que recusa ou escopo truncado não pode
	@# impedir o recálculo, senão a base fica coletada e sem nota.
	-@$(MAKE) --no-print-directory sweep
	@echo ""
	@echo "==> 3/5  Recalculando notas e buscando qpreço e vizinhança."
	@$(MAKE) --no-print-directory score
	@echo ""
	@echo "==> 4/5  Registrando desfechos: anúncio que saiu do ar contra ITBI."
	@echo "         Não responde no mesmo dia — o ITBI atrasa dois meses."
	-@$(MAKE) --no-print-directory desfechos
	@echo ""
	@echo "==> 5/5  Aferindo o fator de área contra os pares do mesmo endereço."
	@PYTHONPATH=. $(PY) scripts/medir_area_itbi.py --cidade "$(CIDADE)"
	@echo ""
	@echo "     Pronto. Confira no JSON do passo 3:"
	@echo "    qpreco_interrompido / similares_interrompido devem ser null."
	@echo "    'bloqueado' significa que o portal recusou — pare antes de repetir."
	@echo "    Cada execução busca no máximo $(QPRECO_LIMIT) qpreços e $(SIMILARES_LIMIT)"
	@echo "    vizinhanças; rode 'make score' de novo nos próximos dias para a fila andar."
	@echo "    Se a mediana do passo 3 sair longe de $(AREA_FATOR_ATUAL), ajuste"
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

## clean: remove venv, caches e containers (preserva o .env)
.PHONY: clean
clean:
	$(COMPOSE) down
	rm -rf $(VENV) .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
