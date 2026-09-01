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

    # Opportunity alerts. An empty smtp_host keeps the job from sending anything.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    smtp_subject_prefix: str = "[ImovelRadar]"


settings = Settings()
