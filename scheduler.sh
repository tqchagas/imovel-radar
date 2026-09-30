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
NEIGHBORHOODS="${SWEEP_NEIGHBORHOODS:-alto_barroca barroca nova_suica santo_agostinho lourdes funcionarios savassi sion anchieta cruzeiro serra santo_antonio gutierrez prado sao_pedro}"
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

neighborhood_args() {
    for name in $NEIGHBORHOODS; do
        printf ' --bairro %s' "$name"
    done
}

log "scheduler up: cidade='${CITY}' fontes='${SOURCES}' intervalo=${INTERVAL}s"
log "garimpo bairros='${NEIGHBORHOODS}'"
log "aguardando ${START_DELAY}s para as migrations do web terminarem"
sleep "$START_DELAY"

while true; do
    started=$(date +%s)

    # Serie do IPCA usada na correcao monetaria do ITBI. Uma queda do BCB nao
    # pode derrubar o ciclo inteiro: a unica consequencia e a referencia ficar
    # um mes atrasada ate o proximo ciclo.
    log "atualizando a serie do IPCA"
    if python -m app.ingestion.cli ipca; then
        log "IPCA em dia"
    else
        log "IPCA falhou (codigo $?), referencia fica no mes anterior"
    fi

    # Keep the existing city-wide apartment catalog fresh for the general
    # opportunities page. The focused garimpo below adds houses and verifies
    # each candidate's individual listing page.
    log "iniciando varredura geral de apartamentos"
    if python -m app.ingestion.cli market-sweep \
        --cidade "$CITY" --uf "$UF" $(source_args) \
        --filtros '{"tipo_imovel": "APARTAMENTO"}' --max-pages "$MAX_PAGES"; then
        log "varredura geral concluida"
    else
        log "varredura geral falhou (codigo $?), seguindo com o ciclo"
    fi

    # Coleta os bairros definidos, apartamentos e casas, e confere a página
    # individual sem contornar bloqueios. Escopos incompletos nunca desativam
    # anúncios; o próximo ciclo tenta novamente.
    log "coletando anúncios convencionais e recalculando o garimpo"
    if python -m app.ingestion.cli flip-garimpo-refresh \
        $(source_args) $(neighborhood_args) --max-pages "$MAX_PAGES"; then
        log "garimpo atualizado"
    else
        log "garimpo falhou (codigo $?), seguindo com o restante do ciclo"
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

    # Contrato da planta quitado anos depois sai das estatisticas. A ingestao
    # ja marca as ruas que recebe; aqui a cidade inteira acompanha a regra
    # da versao que esta no ar.
    # Codigo 3 e o comando avisando que o total de marcas saltou mais de 20%.
    log "marcando registros tardios de ITBI"
    status=0
    python -m app.ingestion.cli marcar-tardios --cidade "$CITY_KEY" || status=$?
    case "$status" in
        0) log "registros tardios em dia" ;;
        3) log "ALERTA: total de registros tardios saltou mais de 20%, confira a regra e o ultimo ITBI" ;;
        *) log "registros tardios falharam (codigo $status)" ;;
    esac

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

    # The general page is refreshed whether or not SMTP alert rules exist.
    log "recalculando oportunidades gerais"
    if python -m app.ingestion.cli opportunity-refresh --cidade "$CITY"; then
        log "oportunidades gerais recalculadas"
    else
        log "recálculo das oportunidades falhou (codigo $?)"
    fi

    log "enviando alertas configurados (se houver)"
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
