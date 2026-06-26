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
    # ``vllm`` selects the dedicated self-hosted provider (full capabilities);
    # ``openai_compatible`` stays the generic catch-all (conservative caps).
    ai_provider: str = "dry_run"
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str = "gpt-4o-mini"
    ai_request_timeout: float = 60.0
    # Connection-establishment timeout (separate from the read timeout above).
    ai_connect_timeout: float = 10.0
    # Bounded retries for SAFE transient failures only (connection error,
    # timeout, selected 5xx). Never used to re-issue a completed call.
    ai_max_retries: int = 2

    # --- Brain event outbox ---
    # Consumer retry budget before an event is dead-lettered (FAILED), the
    # batch size per pass, and the background worker's poll interval (seconds).
    brain_event_max_attempts: int = 5
    brain_worker_batch: int = 500
    brain_worker_interval: float = 2.0
    # --- Brain state compiler (Prompt 5) ---
    # Bump this string whenever the deterministic compilation logic or token
    # budgets change so existing checksums/versions are intentionally invalidated.
    brain_compiler_version: str = "det-v1"
    brain_compiler_batch: int = 50
    brain_compiler_max_attempts: int = 3
    # Optional LLM prose-compression of the (already deterministic) summary. Off
    # by default — the compiler is fully deterministic without it.
    brain_compiler_use_llm: bool = False
    # --- Brain Gateway (Prompt 7: OpenAI-compatible surface for LibreChat) ---
    # Per-user, per-process rate + concurrency limits (these do NOT span uvicorn
    # workers / replicas — the effective limit is multiplied by the worker count).
    brain_gateway_rate_per_min: int = 60
    brain_gateway_burst: int = 20
    brain_gateway_max_concurrency: int = 4
    # The model id the gateway advertises and accepts (decouples LibreChat's
    # configured model name from whatever upstream model the provider serves).
    brain_gateway_model: str = "supervoid-brain"

    # --- Integration hub ---
    # Local-first by default: external network operations (webhook dispatch,
    # ComfyUI queueing, remote GitHub sync) are *recorded* rather than fired
    # unless this is explicitly enabled. Internal mutations (asset/provenance
    # creation, task links, local export/import packages) always run for real
    # once their operation has been approved.
    integrations_allow_network: bool = False
    # Root for generated/ingested desktop file-exchange packages (under storage).
    integrations_exchange_subdir: str = "integrations/exchange"
    integrations_request_timeout: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
