import json
from datetime import datetime

import typer

from app.db.session import SessionLocal
from app.ingestion.belo_horizonte import CITY as BELO_HORIZONTE_CITY
from app.ingestion.belo_horizonte import parse_file as parse_belo_horizonte
from app.ingestion.loader import load_transactions
from app.pricing.quintoandar import enrich_quintoandar_price_suggestions
from app.market_collectors import MarketQuery
from app.market_collectors.normalize import SUPPORTED_QUERY_FILTERS
from app.services.market_refresh import COLLECTORS, collect_and_refresh
from app.services.opportunities import refresh_opportunities
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
    source: list[str] = typer.Option(["quintoandar", "vivareal"]),
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


@app.command("opportunity-config")
def opportunity_config(
    cidade: str = typer.Option(...),
    destinatario: list[str] = typer.Option(..., help="Pode ser repetido."),
    bairro: list[str] = typer.Option([]),
    desconto_minimo_pct: float = typer.Option(0.15),
    confianca_minima: str = typer.Option("media"),
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
    sources=("quintoandar", "vivareal"),
    filtros: dict | None = None,
    max_pages: int = 100,
    deactivate: bool = True,
    skip_refresh: bool = False,
    dry_run: bool = False,
    force_initial: bool = False,
    sender=None,
    now: datetime | None = None,
    progress=None,
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

    report["opportunities"] = refresh_opportunities(db, city=cidade)
    log(
        f"oportunidades: calculadas={report['opportunities']['calculated']} "
        f"elegiveis={report['opportunities']['eligible']}"
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
    source: list[str] = typer.Option(["quintoandar", "vivareal"]),
    bairro: list[str] = typer.Option([]),
    filtros: str = typer.Option("{}", help="Filtros extras em JSON."),
    max_pages: int = typer.Option(100),
    no_deactivate: bool = typer.Option(False, "--no-deactivate"),
    skip_refresh: bool = typer.Option(False, "--skip-refresh"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force_initial: bool = typer.Option(False, "--force-initial"),
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
        )
    finally:
        db.close()
    if report["status"] != "ok":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
