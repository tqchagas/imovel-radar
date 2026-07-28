from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://imovelradar:imovelradar@localhost:5433/imovelradar"
    )
    quintoandar_price_suggestion_cookie: str = ""


settings = Settings()
