import json

import typer

from app.db.session import SessionLocal
from app.ingestion.belo_horizonte import CITY as BELO_HORIZONTE_CITY
from app.ingestion.belo_horizonte import parse_file as parse_belo_horizonte
from app.ingestion.loader import load_transactions
from app.pricing.quintoandar import enrich_quintoandar_price_suggestions
from app.market_collectors import CollectionResult, MarketQuery
from app.market_collectors.normalize import canonical_scope_key
from app.services.market_refresh import COLLECTORS, refresh_market

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
    try:
        parsed_filters = json.loads(filtros)
        if not isinstance(parsed_filters, dict):
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise typer.BadParameter("filtros deve ser um objeto JSON") from exc

    unknown = [name for name in source if name not in COLLECTORS]
    if unknown:
        raise typer.BadParameter(f"Unknown source(s) {unknown}. Available: {list(COLLECTORS)}")

    neighborhoods = bairro or [None]
    db = SessionLocal()
    try:
        for name in source:
            collected = []
            for neighborhood in neighborhoods:
                query = MarketQuery(
                    uf=uf,
                    cidade=cidade,
                    bairro=neighborhood,
                    tipo_imovel=parsed_filters.get("tipo_imovel"),
                    quartos=parsed_filters.get("quartos"),
                    area_util_m2=parsed_filters.get("area_util_m2"),
                    max_pages=max_pages,
                    source=name,
                    filtros=parsed_filters,
                )
                collected.append(COLLECTORS[name](query))
            merged = CollectionResult(
                source=name,
                listings=[item for item in collected for item in item.listings],
                success=all(item.success for item in collected),
                partial=any(item.partial for item in collected),
                scope_key=canonical_scope_key(
                    MarketQuery(
                        uf=uf,
                        cidade=cidade,
                        bairros=tuple(bairro),
                        source=name,
                        filtros=parsed_filters,
                    ),
                    name,
                ),
                pages=sum(item.pages for item in collected),
                error="; ".join(item.error for item in collected if item.error) or None,
            )
            summary = refresh_market(
                db,
                merged,
                deactivate=not no_deactivate,
                query=MarketQuery(
                    uf=uf,
                    cidade=cidade,
                    bairros=tuple(bairro),
                    source=name,
                    filtros=parsed_filters,
                ),
            )
            typer.echo(
                f"{name}: status={summary['status']} seen={summary['seen']} "
                f"deactivated={summary['deactivated']}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    app()
