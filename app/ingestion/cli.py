import json
from datetime import datetime

import typer

from app.db.session import SessionLocal
from app.domain.opportunities import MIN_DISCOUNT_PCT, MIN_SCORE
from app.ingestion.belo_horizonte import CITY as BELO_HORIZONTE_CITY
from app.ingestion.belo_horizonte import parse_file as parse_belo_horizonte
from app.ingestion.loader import load_transactions
from app.pricing.quintoandar import (
    enrich_quintoandar_price_suggestions,
    price_suggestion_updater,
)
from app.pricing.similar_houses import similar_houses_updater
from app.market_collectors import MarketQuery
from app.market_collectors.normalize import SUPPORTED_QUERY_FILTERS
from app.services.market_coverage import neighborhoods_with_itbi, sweep_city
from app.services.outcomes import match_pending_outcomes, record_delistings
from app.services.registry_sync import sync_registry
from app.services.market_refresh import COLLECTORS, collect_and_refresh
from app.services.opportunities import (
    QPRECO_FETCH_LIMIT,
    SIMILARES_FETCH_LIMIT,
    refresh_opportunities,
)
from app.services.opportunity_notifications import (
    load_config,
    send_opportunity_alerts,
    upsert_alert_config,
)

app = typer.Typer()

ADAPTERS = {
    BELO_HORIZONTE_CITY: parse_belo_horizonte,
}


@app.command()
def ingest(
    city: str = typer.Option(...),
    file: str = typer.Option(...),
) -> None:
    if city not in ADAPTERS:
        raise typer.BadParameter(f"Unknown city '{city}'. Available: {list(ADAPTERS)}")

    records = ADAPTERS[city](file)
    db = SessionLocal()
    try:
        inserted = load_transactions(db, records)
        typer.echo(f"Inserted {inserted} new transactions for {city}")
    finally:
        db.close()


@app.command()
def quintoandar_price_suggestions(
    limit: int = typer.Option(100),
    workers: int = typer.Option(1),
    worker_index: int = typer.Option(0),
    cidade: list[str] = typer.Option([]),
) -> None:
    db = SessionLocal()
    try:
        result = enrich_quintoandar_price_suggestions(
            db,
            limit=limit,
            workers=workers,
            worker_index=worker_index,
            cidades=cidade,
            progress=typer.echo,
        )
        typer.echo(json.dumps(result, ensure_ascii=False))
    finally:
        db.close()


def qpreco_fetcher(enabled: bool):
    """The price-suggestion endpoint answers without a session, so the cookie
    is an optional extra: only `--sem-qpreco` turns the second reference off."""
    if not enabled:
        return None
    return price_suggestion_updater()


def similares_fetcher(enabled: bool):
    """O contexto de vizinhança não exige sessão nem id do QuintoAndar: ele
    pergunta por coordenada, então vale para as três fontes."""
    return similar_houses_updater() if enabled else None


def _parse_filters(filtros: str) -> dict:
    try:
        parsed = json.loads(filtros)
        if not isinstance(parsed, dict):
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter("filtros deve ser um objeto JSON") from exc
    unknown = sorted(set(parsed) - SUPPORTED_QUERY_FILTERS)
    if unknown:
        raise typer.BadParameter(f"Filtro desconhecido: {unknown[0]}")
    return parsed


@app.command("market-refresh")
def market_refresh(
    source: list[str] = typer.Option(["loft", "quintoandar", "vivareal"]),
    cidade: str = typer.Option(...),
    uf: str = typer.Option("MG"),
    bairro: list[str] = typer.Option([]),
    filtros: str = typer.Option("{}", help="Filtros extras em JSON."),
    max_pages: int = typer.Option(100),
    no_deactivate: bool = typer.Option(False, "--no-deactivate"),
) -> None:
    parsed_filters = _parse_filters(filtros)

    unknown = [name for name in source if name not in COLLECTORS]
    if unknown:
        raise typer.BadParameter(f"Unknown source(s) {unknown}. Available: {list(COLLECTORS)}")

    db = SessionLocal()
    try:
        for name in source:
            summary = collect_and_refresh(
                db,
                MarketQuery(
                    uf=uf,
                    cidade=cidade,
                    bairros=tuple(bairro),
                    source=name,
                    max_pages=max_pages,
                    tipo_imovel=parsed_filters.get("tipo_imovel"),
                    quartos=parsed_filters.get("quartos"),
                    area_util_m2=parsed_filters.get("area_util_m2"),
                    filtros=parsed_filters,
                ),
                deactivate=not no_deactivate,
            )
            typer.echo(
                f"{name}: status={summary['status']} seen={summary['seen']} "
                f"deactivated={summary['deactivated']}"
            )
    finally:
        db.close()


@app.command("market-sweep")
def market_sweep(
    source: list[str] = typer.Option(["loft", "quintoandar", "vivareal"]),
    cidade: str = typer.Option(...),
    uf: str = typer.Option("MG"),
    filtros: str = typer.Option("{}", help="Filtros extras em JSON."),
    max_pages: int = typer.Option(100),
    min_vendas_bairro: int = typer.Option(30, help="ITBI mínimo para valer a coleta."),
    no_deactivate: bool = typer.Option(False, "--no-deactivate"),
    no_split: bool = typer.Option(False, "--no-split", help="Não dividir escopos truncados."),
) -> None:
    """Varre a cidade inteira por bairro, respeitando os tetos dos portais."""
    parsed_filters = _parse_filters(filtros)
    unknown = [name for name in source if name not in COLLECTORS]
    if unknown:
        raise typer.BadParameter(f"Unknown source(s) {unknown}. Available: {list(COLLECTORS)}")

    db = SessionLocal()
    try:
        bairros = neighborhoods_with_itbi(db, cidade, min_sales=min_vendas_bairro)
        if not bairros:
            typer.echo(f"Nenhum bairro de {cidade} tem ITBI suficiente para comparar.")
            raise typer.Exit(code=1)
        typer.echo(f"{len(bairros)} bairros com ITBI suficiente.")
        for name in source:
            report = sweep_city(
                db,
                MarketQuery(
                    uf=uf,
                    cidade=cidade,
                    source=name,
                    max_pages=max_pages,
                    tipo_imovel=parsed_filters.get("tipo_imovel"),
                    quartos=parsed_filters.get("quartos"),
                    area_util_m2=parsed_filters.get("area_util_m2"),
                    filtros=parsed_filters,
                ),
                neighborhoods=bairros,
                deactivate=not no_deactivate,
                split_on_cap=not no_split,
                progress=typer.echo,
            )
            typer.echo(
                f"{name}: bairros={report['neighborhoods']} completos={report['collected']} "
                f"truncados={report['capped']} vazios={report['empty']} "
                f"falhas={report['failed']} anuncios={report['seen']}"
            )
            if report["empty"]:
                typer.echo(
                    f"  {report['empty']} escopo(s) voltaram vazios — normalmente o nome do "
                    f"bairro no ITBI não casa com o do portal. Colete uma vez com loft ou "
                    f"quintoandar (que ignoram caixa e acento) para aprender a grafia."
                )
    finally:
        db.close()


@app.command("opportunity-refresh")
def opportunity_refresh(
    cidade: str = typer.Option(...),
    source: str = typer.Option(None, help="Limita a uma fonte; padrão é todas."),
    nota_minima: int = typer.Option(MIN_SCORE, help="Nota mínima (0-100) para alertar."),
    qpreco: bool = typer.Option(
        True, "--qpreco/--sem-qpreco", help="Consultar a estimativa do QuintoAndar."
    ),
    qpreco_limit: int = typer.Option(
        QPRECO_FETCH_LIMIT, help="Teto de consultas ao QuintoAndar por execução."
    ),
    similares: bool = typer.Option(
        True, "--similares/--sem-similares",
        help="Buscar o contexto de vizinhança (vale para as três fontes).",
    ),
    similares_limit: int = typer.Option(
        SIMILARES_FETCH_LIMIT, help="Teto de consultas de vizinhança por execução."
    ),
) -> None:
    """Recalcula notas e descontos. Não envia e-mail nem exige configuração."""
    db = SessionLocal()
    try:
        result = refresh_opportunities(
            db,
            city=cidade,
            source=source,
            min_nota=nota_minima,
            qpreco_fetcher=qpreco_fetcher(qpreco),
            qpreco_limit=qpreco_limit,
            similares_fetcher=similares_fetcher(similares),
            similares_limit=similares_limit,
        )
        typer.echo(json.dumps(result, ensure_ascii=False, default=str))
    finally:
        db.close()


@app.command("opportunity-config")
def opportunity_config(
    cidade: str = typer.Option(...),
    destinatario: list[str] = typer.Option(..., help="Pode ser repetido."),
    bairro: list[str] = typer.Option([]),
    desconto_minimo_pct: float = typer.Option(MIN_DISCOUNT_PCT),
    confianca_minima: str = typer.Option("baixa"),
    nota_minima: int = typer.Option(80, help="Nota mínima (0-100) para alertar."),
    periodicidade_minutos: int = typer.Option(720),
    timezone_name: str = typer.Option("America/Sao_Paulo", "--timezone"),
    disabled: bool = typer.Option(False, "--disabled"),
) -> None:
    db = SessionLocal()
    try:
        config = upsert_alert_config(
            db,
            cidade=cidade,
            destinatarios=list(destinatario),
            bairros=list(bairro),
            desconto_minimo_pct=desconto_minimo_pct,
            confianca_minima=confianca_minima,
            nota_minima=nota_minima,
            periodicidade_minutos=periodicidade_minutos,
            timezone_name=timezone_name,
            enabled=not disabled,
        )
        typer.echo(
            f"config: cidade={config.cidade} rule_version={config.rule_version} "
            f"enabled={config.enabled}"
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    finally:
        db.close()


def run_opportunity_alerts(
    db,
    *,
    cidade: str,
    uf: str = "MG",
    bairros=(),
    sources=("loft", "quintoandar", "vivareal"),
    filtros: dict | None = None,
    max_pages: int = 100,
    deactivate: bool = True,
    skip_refresh: bool = False,
    dry_run: bool = False,
    force_initial: bool = False,
    sender=None,
    now: datetime | None = None,
    progress=None,
    **opportunity_options,
) -> dict:
    """Collect, recalculate and alert in one pass, isolating failures per source."""
    report = {"status": "ok", "collections": [], "opportunities": {}, "alerts": {}}
    log = progress or (lambda message: None)

    # An absent or disabled configuration stops the job before any destructive step.
    if load_config(db) is None:
        report["status"] = "disabled"
        log("configuração de alertas ausente ou desabilitada")
        db.rollback()
        return report
    db.rollback()

    parsed_filters = dict(filtros or {})
    if not skip_refresh:
        for name in sources:
            try:
                summary = collect_and_refresh(
                    db,
                    MarketQuery(
                        uf=uf,
                        cidade=cidade,
                        bairros=tuple(bairros),
                        source=name,
                        max_pages=max_pages,
                        tipo_imovel=parsed_filters.get("tipo_imovel"),
                        quartos=parsed_filters.get("quartos"),
                        area_util_m2=parsed_filters.get("area_util_m2"),
                        filtros=parsed_filters,
                    ),
                    deactivate=deactivate,
                )
            except Exception as error:  # noqa: BLE001 - one source must not stop the others
                db.rollback()
                summary = {"source": name, "status": "failed", "error": str(error)}
            report["collections"].append(summary)
            log(f"{name}: status={summary['status']}")

    report["opportunities"] = refresh_opportunities(db, city=cidade, **opportunity_options)
    log(
        f"oportunidades: calculadas={report['opportunities']['calculated']} "
        f"elegiveis={report['opportunities']['eligible']} "
        f"qpreco={report['opportunities']['qpreco_buscados']} "
        f"qpreco_falhas={report['opportunities']['qpreco_falhas']} "
        f"qpreco_interrompido={report['opportunities']['qpreco_interrompido'] or '-'}"
    )
    report["alerts"] = send_opportunity_alerts(
        db, sender=sender, now=now, dry_run=dry_run, force_initial=force_initial
    )
    log(
        f"alertas: enviados={report['alerts']['sent']} "
        f"falhas={report['alerts']['failed']} ignorados={report['alerts']['skipped']}"
    )
    return report


@app.command("opportunity-alerts")
def opportunity_alerts(
    cidade: str = typer.Option(...),
    uf: str = typer.Option("MG"),
    source: list[str] = typer.Option(["loft", "quintoandar", "vivareal"]),
    bairro: list[str] = typer.Option([]),
    filtros: str = typer.Option("{}", help="Filtros extras em JSON."),
    max_pages: int = typer.Option(100),
    no_deactivate: bool = typer.Option(False, "--no-deactivate"),
    skip_refresh: bool = typer.Option(False, "--skip-refresh"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force_initial: bool = typer.Option(False, "--force-initial"),
    qpreco: bool = typer.Option(
        True, "--qpreco/--sem-qpreco", help="Consultar a estimativa do QuintoAndar."
    ),
    qpreco_limit: int = typer.Option(
        QPRECO_FETCH_LIMIT, help="Teto de consultas ao QuintoAndar por execução."
    ),
) -> None:
    parsed_filters = _parse_filters(filtros)
    unknown = [name for name in source if name not in COLLECTORS]
    if unknown:
        raise typer.BadParameter(f"Unknown source(s) {unknown}. Available: {list(COLLECTORS)}")

    db = SessionLocal()
    try:
        report = run_opportunity_alerts(
            db,
            cidade=cidade,
            uf=uf,
            bairros=bairro,
            sources=source,
            filtros=parsed_filters,
            max_pages=max_pages,
            deactivate=not no_deactivate,
            skip_refresh=skip_refresh,
            dry_run=dry_run,
            force_initial=force_initial,
            progress=typer.echo,
            qpreco_fetcher=qpreco_fetcher(qpreco),
            qpreco_limit=qpreco_limit,
        )
    finally:
        db.close()
    if report["status"] != "ok":
        raise typer.Exit(code=1)


@app.command("outcome-track")
def outcome_track(
    cidade: str = typer.Option("belo_horizonte", help="Cidade, na forma armazenada."),
) -> None:
    """Registra as saídas de anúncio e procura a quitação de ITBI de cada uma.

    É a única medida do projeto que diz se um alerta prestou, em vez de se uma
    estimativa acertou outro número estimado. Não dá resposta no mesmo dia: o
    ITBI chega com dois meses de atraso, então um desfecho aberto hoje só fecha
    meses adiante. Rode a cada ciclo de coleta.
    """
    db = SessionLocal()
    try:
        abertos = record_delistings(db, city=cidade)
        resumo = match_pending_outcomes(db, city=cidade)
    finally:
        db.close()
    typer.echo(json.dumps({"registrados": abertos, **resumo}, ensure_ascii=False))


@app.command("registry-sync")
def registry_sync(
    cidade: str = typer.Option("belo_horizonte", help="Cidade, na forma armazenada."),
    regional: str = typer.Option(
        None, help="Sincroniza só uma regional (barreiro, centro_sul, ...). Vazio = todas."
    ),
    se_nova: bool = typer.Option(
        False,
        "--se-nova",
        help="Só baixa se o CKAN publicou uma extração mais nova do que a gravada.",
    ),
) -> None:
    """Baixa o cadastro imobiliário da prefeitura e grava os endereços com coordenada.

    É o que permite ao anúncio que publica rua e ponto, mas não o número -
    Loft e QuintoAndar - alcançar o tier de endereço exato. Rode uma vez por
    mês: a prefeitura publica uma extração nova por mês.
    """
    db = SessionLocal()
    try:
        resumo = sync_registry(db, city=cidade, regional=regional, skip_if_current=se_nova)
    finally:
        db.close()
    typer.echo(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    app()
