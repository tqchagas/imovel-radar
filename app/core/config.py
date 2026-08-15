from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://imovelradar:imovelradar@localhost:5433/imovelradar"
    )
    quintoandar_price_suggestion_cookie: str = ""
    public_base_url: str = "http://localhost:8000"
    # Off by default so tests and local shells do not scan 500k rows on import.
    warm_curiosities_on_startup: bool = False


settings = Settings()
