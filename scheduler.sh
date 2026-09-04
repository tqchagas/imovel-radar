#!/bin/sh
# Periodic collection loop.
#
# Runs in its own container off the same image as the web service. A plain
# sleep loop rather than cron: there is exactly one job here, the container
# restart policy already covers crashes, and the logs go straight to
# `docker compose logs` instead of a file nobody reads.
#
# The web container owns migrations, so this one waits for the schema rather
# than racing it.
set -eu

CITY="${SWEEP_CITY:-Belo Horizonte}"
# A forma como a cidade e gravada: minuscula, sem acento, com sublinhado.
CITY_KEY="${SWEEP_CITY_KEY:-belo_horizonte}"
UF="${SWEEP_UF:-MG}"
SOURCES="${SWEEP_SOURCES:-loft quintoandar vivareal}"
INTERVAL="${SWEEP_INTERVAL_SECONDS:-86400}"
MAX_PAGES="${SWEEP_MAX_PAGES:-100}"
FILTERS="${SWEEP_FILTERS:-{\"tipo_imovel\": \"APARTAMENTO\"\}}"
START_DELAY="${SWEEP_START_DELAY_SECONDS:-60}"
# Teto de paginas de condominio por ciclo. Sao 19.117 predios em BH e a coleta
# e dirigida pelo anuncio sem numero, entao ela converge em poucos ciclos.
CONDO_LIMIT="${CONDO_LIMIT:-500}"

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
}

source_args() {
    for name in $SOURCES; do
        printf ' --source %s' "$name"
    done
}

log "scheduler up: cidade='${CITY}' fontes='${SOURCES}' intervalo=${INTERVAL}s"
log "aguardando ${START_DELAY}s para as migrations do web terminarem"
sleep "$START_DELAY"

while true; do
    started=$(date +%s)

    # A failing sweep must not kill the loop: the portals throttle and time out,
    # and the next cycle is the retry.
    log "iniciando varredura"
    if python -m app.ingestion.cli market-sweep \
        --cidade "$CITY" --uf "$UF" $(source_args) \
        --filtros "$FILTERS" --max-pages "$MAX_PAGES"; then
        log "varredura concluida"
    else
        log "varredura falhou (codigo $?), seguindo para os alertas mesmo assim"
    fi

    # Cadastro imobiliario da prefeitura: e o que faz o anuncio sem numero de
    # rua alcancar o tier de endereco. Os dez arquivos somam quase
    # quatrocentos megabytes e a prefeitura publica uma extracao por mes,
    # entao o ciclo diario so baixa quando ha uma mais nova do que a gravada.
    log "sincronizando o cadastro imobiliario (so se houver extracao nova)"
    if python -m app.ingestion.cli registry-sync --cidade "$CITY_KEY" --se-nova; then
        log "cadastro em dia"
    else
        log "cadastro falhou (codigo $?), seguindo mesmo assim"
    fi

    # Diretorio de condominios do portal: e daqui que sai o numero da rua que
    # Loft e QuintoAndar nao publicam. Roda depois da varredura, que e quem
    # cria a demanda, e antes do calculo das notas, que e quem a consome. Sao
    # 19.117 predios em BH e cada execucao tem teto, entao a cobertura cresce
    # a cada ciclo em vez de sair completa do primeiro.
    log "coletando paginas de condominio (teto de $CONDO_LIMIT)"
    if python -m app.ingestion.cli condo-sync --cidade "$CITY_KEY" --limit "$CONDO_LIMIT"; then
        log "condominios atualizados"
    else
        log "condominios falharam (codigo $?), seguindo mesmo assim"
    fi

    # Registra as saidas de anuncio e procura a quitacao de ITBI de cada uma.
    # Nao devolve resposta no mesmo dia: o ITBI chega com dois meses de atraso,
    # entao um desfecho aberto hoje so fecha meses adiante. Roda antes dos
    # alertas porque nao depende deles e nao pode ser perdido se eles falharem.
    log "registrando desfechos de anuncios"
    if python -m app.ingestion.cli outcome-track --cidade "$CITY_KEY"; then
        log "desfechos atualizados"
    else
        log "desfechos falharam (codigo $?)"
    fi

    # Recalculates and emails. Does nothing when no alert config is enabled.
    log "recalculando oportunidades e enviando alertas"
    if python -m app.ingestion.cli opportunity-alerts \
        --cidade "$CITY" --uf "$UF" $(source_args) --skip-refresh; then
        log "alertas concluidos"
    else
        log "alertas falharam (codigo $?)"
    fi

    elapsed=$(( $(date +%s) - started ))
    remaining=$(( INTERVAL - elapsed ))
    if [ "$remaining" -lt 60 ]; then
        # The cycle took longer than the interval; give the portals a breather
        # instead of starting again immediately.
        remaining=60
    fi
    log "ciclo levou ${elapsed}s, proximo em ${remaining}s"
    sleep "$remaining"
done
