import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy import URL

DEFAULT_JWT_SECRET = "insecure-dev-secret-change-me-in-production"


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    app_name: str = "Voice of Finance API"
    environment: str = "development"  # development | staging | production
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    # Comma separated list or JSON array.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # --- Database ---
    # Any async SQLAlchemy URL. For Supabase use the "Session pooler" or direct
    # connection string with the `postgresql+asyncpg://` scheme.
    # If DATABASE_URL is not set it is assembled from the POSTGRES_* variables.
    database_url: str = ""
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "voice_of_finance"
    # Set to true when connecting through PgBouncer in transaction mode
    # (e.g. Supabase "Transaction pooler", port 6543).
    database_pgbouncer: bool = False
    database_echo: bool = False

    # --- Auth ---
    jwt_secret_key: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # --- AI providers ---
    openai_api_key: str | None = None
    whisper_model: str = "whisper-1"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_max_tokens: int = 8000

    # --- Extraction ---
    audio_workdir: str = "/tmp/voice-of-finance-audio"
    # Whisper API upload limit is 25 MB; audio is split into chunks below this.
    whisper_max_chunk_mb: int = 24
    whisper_chunk_seconds: int = 600
    max_video_duration_seconds: int = 3 * 60 * 60
    transcript_max_chars_for_llm: int = 400_000

    # --- Community / reputation ---
    reputation_per_upvote: int = 5
    reputation_per_downvote: int = -2
    reputation_per_comment: int = 1
    analyst_verification_threshold: int = 100

    # --- Billing ---
    # MVP: when enabled, users can self-upgrade to premium without payment.
    # Disable in production once a payment provider (e.g. Stripe) is wired in.
    billing_mock_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _build_database_url(self) -> "Settings":
        value = self.database_url
        if not value:
            # Positional args: drivername, username, secret, host, port, database.
            value = URL.create(
                "postgresql+asyncpg",
                self.postgres_user,
                self.postgres_password,
                self.postgres_host,
                self.postgres_port,
                self.postgres_db,
            ).render_as_string(hide_password=False)
        # Accept plain `postgres://` / `postgresql://` URLs (Supabase, Railway, Fly)
        # and convert them to the asyncpg driver.
        if value.startswith("postgres://"):
            value = "postgresql://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://") :]
        self.database_url = value

        if self.is_production and self.jwt_secret_key == DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET_KEY must be set to a strong random value in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
