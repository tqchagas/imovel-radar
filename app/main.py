from fastapi import FastAPI

from app.api.routes.transactions import router as transactions_router

app = FastAPI(title="ImovelRadar API")
app.include_router(transactions_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
