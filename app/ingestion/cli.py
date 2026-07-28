import json

import typer

from app.db.session import SessionLocal
from app.ingestion.belo_horizonte import CITY as BELO_HORIZONTE_CITY
from app.ingestion.belo_horizonte import parse_file as parse_belo_horizonte
from app.ingestion.loader import load_transactions
from app.pricing.quintoandar import enrich_quintoandar_price_suggestions

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


if __name__ == "__main__":
    app()
