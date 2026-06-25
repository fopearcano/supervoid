from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "SUPERVOID Publishing"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True

    api_prefix: str = "/api"

    database_url: str = f"sqlite:///{(BASE_DIR / 'supervoid.db').as_posix()}"
    database_echo: bool = False

    # How the schema is prepared at application startup:
    #   create_all -> SQLModel.metadata.create_all (fast, fresh dev DBs; default)
    #   migrate    -> Alembic; non-destructively adopts a legacy DB then upgrades
    #   skip       -> do nothing (migrations run out-of-band, e.g. in deploy/CI)
    # ``create_all`` keeps the current developer experience; production/managed
    # deployments set ``migrate`` (or ``skip`` + run migrations explicitly).
    db_init_strategy: str = "create_all"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Authentication — development defaults. Override via environment in
    # any non-development deployment.
    secret_key: str = "supervoid-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Local file storage root. Real uploads land under this directory;
    # placeholder attachment records do not touch disk.
    storage_path: str = (BASE_DIR / "storage").as_posix()

    # Logging
    log_level: str = "INFO"

    # --- AI integration ---
    # ``dry_run`` ships canned responses without touching the network and is
    # the default for the foundation. Set to ``openai`` / ``openrouter`` /
    # ``lm_studio`` / ``openai_compatible`` to talk to a real backend.
    ai_provider: str = "dry_run"
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str = "gpt-4o-mini"
    ai_request_timeout: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
