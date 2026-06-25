from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str  # M4: no default — must be set via DATABASE_URL env var
    redis_url: str = "redis://localhost:6379"
    api_key_pepper: str = ""  # M3: HMAC pepper for API key hashing
    validation_threshold: int = 2
    app_name: str = "CommonTrace"
    debug: bool = False
    embedding_dimensions: int = 1536
    rate_limit_read_per_minute: int = 60
    rate_limit_write_per_minute: int = 20
    api_key_header_name: str = "X-API-Key"
    openai_api_key: str = ""

    # Admin dashboard token — gates /api/v1/admin/* endpoints. Empty disables admin routes.
    admin_dashboard_token: str = ""

    # Temporal decay
    temporal_decay_default_half_life_days: int = 365

    # Consolidation worker
    consolidation_interval_hours: int = 24
    consolidation_stale_age_days: int = 180

    # Savings & Impact — USD per 1M tokens. Single published price constant;
    # the skill's DEFAULT_PRICE_PER_MTOK mirrors this value. Override via
    # the SAVINGS_PRICE_PER_MTOK env var.
    savings_price_per_mtok: float = 5.0


settings = Settings()
