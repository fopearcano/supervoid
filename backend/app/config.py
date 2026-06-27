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

    # --- Supervised agent framework: model-driven runner limits (Prompt 9) ---
    # Strict bounds on the model-driven reasoning loop. A run can request
    # read-only tools and feed results back to the model, but never beyond these
    # ceilings — guarding against runaway loops, context blow-up, and long calls.
    agent_max_tool_rounds: int = 3          # model<->tool round trips per run
    agent_max_tool_calls: int = 8           # total read-only tool executions per run
    agent_max_context_chars: int = 24000    # cap on the accumulated prompt size
    agent_max_runtime_seconds: float = 30.0  # wall-clock ceiling for one run
    # Per-model-call timeout passed to the provider (real backends only).
    agent_model_timeout_seconds: float = 20.0

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

    # --- SUPERVOID MCP server (Prompt 10: governed tools for LibreChat) ---
    mcp_enabled: bool = True
    mcp_server_name: str = "supervoid"
    # The internal LibreChat <-> MCP service credential. LibreChat sends it as the
    # X-SUPERVOID-Service-Token header AND uses it to HMAC-sign the user-context
    # headers. Unset => the MCP server fails closed (refuses every request). Set
    # via the MCP_SERVICE_TOKEN env var in deployment; never commit a real value.
    mcp_service_token: str | None = None

    # --- Private navigation / LibreChat hand-off (Prompt 12) ---
    # Where the reverse proxy serves the LibreChat (Brain) UI. The hand-off
    # landing redirects here after binding the conversation. A path (default) or
    # an absolute internal subdomain URL.
    librechat_public_url: str = "/brain/"
    # Lifetime of a signed hand-off token (seconds). Short by design.
    brain_handoff_ttl_seconds: int = 120

    # --- Conversation memory & decision extraction (Prompt 13) ---
    # After each completed Brain response a memory-analysis job runs (via the
    # outbox worker). It PROPOSES durable items into a review inbox; nothing is
    # promoted to verified memory automatically except a low-risk same-user
    # preference whose confidence clears the threshold below. Canon / rights /
    # production claims never become memory — they become PROPOSED decisions
    # that need approval.
    brain_memory_analysis_enabled: bool = True
    # Optional model override for the extraction step (defaults to ``ai_model``).
    brain_memory_analysis_model: str | None = None
    # Auto-accept a member preference only at/above this confidence (and only
    # when low-risk, same-user, non-canon, non-permission, uncontradicted).
    brain_memory_auto_accept_min_confidence: float = 0.85
    # Hard cap on proposals minted from a single turn (anti-spam / anti-runaway).
    brain_memory_max_candidates_per_turn: int = 12
    # How many recent conversation turns to feed the extraction model.
    brain_memory_recent_turns: int = 6

    # --- Cold-detail retrieval (Prompt 14: pgvector evidence system) ---
    # An EXCEPTIONAL evidence layer, not a per-turn reconstruction. Indexing runs
    # asynchronously off the outbox; retrieval is only invoked under explicit
    # triggers (historical justification / detailed source / insufficient
    # evidence / agent request) and never re-fetches what is already in the
    # compiled state.
    retrieval_enabled: bool = True
    # Embedding provider, kept SEPARATE from the conversational model so a small
    # local embedding model can be served on its own endpoint. "dry_run" is a
    # deterministic offline embedder (tests + air-gapped dev); set
    # "openai_compatible" + embedding_base_url for a real TEI/llama.cpp/vLLM
    # embedding server in production.
    embedding_provider: str = "dry_run"
    embedding_model: str = "supervoid-embed-small"
    embedding_dim: int = 384
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_request_timeout: float = 30.0
    embedding_batch_size: int = 64
    # Chunking.
    retrieval_chunk_chars: int = 1200
    retrieval_chunk_overlap: int = 150
    # Search shape.
    retrieval_candidates: int = 40         # structured/ANN candidate pool size
    retrieval_top_k: int = 6               # results handed to the model
    retrieval_min_score: float = 0.0       # drop hits below this blended score
    retrieval_text_weight: float = 0.4     # FTS weight in the hybrid blend
    retrieval_vector_weight: float = 0.6   # vector weight in the hybrid blend
    retrieval_rerank: bool = True          # optional rerank pass
    # Vector backend: "auto" picks pgvector on PostgreSQL, else the in-process
    # cosine fallback. Force "memory" to disable pgvector even on Postgres.
    retrieval_vector_backend: str = "auto"

    # --- Identity linking & member administration (Prompt 15) ---
    # The MCP server maps a LibreChat identity to a SUPERVOID user THROUGH an
    # active admin-managed identity link. With this on (default), an unlinked
    # LibreChat identity is rejected. Turn off only for a controlled migration.
    mcp_require_identity_link: bool = True
    # Suspicious-burst detection: N failures from one principal within the window
    # raises an additional CRITICAL "repeated_failures" security event.
    security_repeated_failure_threshold: int = 5
    security_repeated_failure_window_seconds: int = 300

    # --- Observability & operational controls (Prompt 16) ---
    # The model's effective context window, advertised in the Ops view (the
    # provider's /health does not report it). GPU / internal topology is NEVER
    # exposed on public endpoints — the Ops surface is admin-only.
    brain_context_limit: int = 8192
    # Optional LibreChat health URL (e.g. http://supervoid-librechat:3080/health);
    # unset → LibreChat health reports "unknown" rather than probing.
    librechat_health_url: str | None = None
    librechat_health_timeout: float = 2.0
    # How many recent assistant turns to sample for latency / TTFT aggregates.
    brain_ops_latency_window: int = 200

    # --- Brain stateful sessions & prefix-cache strategy (Prompt 8) ---
    # vLLM prefix caching is an optimisation we make ELIGIBLE — never durable
    # memory. These windows drive the hot/warm/cold lifecycle.
    brain_session_hot_window_minutes: int = 30        # idle ≤ this ⇒ HOT
    brain_session_warm_window_hours: int = 72         # idle ≤ this (+ checkpoint) ⇒ WARM
    brain_session_archive_horizon_days: int = 14      # COLD past this ⇒ archive conversation
    brain_session_compact_after_turns: int = 40       # suggest compaction beyond this
    brain_session_compaction_use_llm: bool = False    # LLM summary is SECONDARY, off by default
    # Prewarming (best-effort vLLM prefix-cache priming; never durable memory).
    brain_prewarm_on_startup: bool = False            # default OFF — keeps dry_run/test path inert
    brain_prewarm_rate_per_min: int = 30
    brain_prewarm_burst: int = 10
    brain_prewarm_batch: int = 25
    brain_prewarm_cooldown_seconds: int = 300         # per-session prewarm debounce

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

    # --- Optional fine-tuning data pipeline (Prompt 18) ---
    # PREPARED, never auto-run. Collection requires explicit per-example approval;
    # an adapter is deployed only when it beats the base on the project evaluation
    # without weakening permissions or approval behaviour. ``tuning_enabled`` gates
    # the collection endpoints; nothing trains or deploys automatically.
    tuning_enabled: bool = False
    tuning_export_subdir: str = "tuning/datasets"   # under storage_path
    tuning_val_fraction: float = 0.2
    tuning_min_examples: int = 10                    # refuse to export a tiny dataset
    # Default LoRA/PEFT training parameters RECORDED with an adapter (not executed).
    tuning_default_base_model: str = "supervoid-brain"
    tuning_lora_rank: int = 16
    tuning_lora_alpha: int = 32
    tuning_lora_dropout: float = 0.05
    tuning_learning_rate: float = 0.0002
    tuning_epochs: int = 3
    # vLLM LoRA serving: where adapters are mounted on the GPU host + rank ceiling.
    tuning_adapter_mount_dir: str = "/opt/brain/adapters"
    tuning_vllm_max_lora_rank: int = 32
    # Deploy gate: minimum project-eval pass rate / correctness an adapter must
    # reach (in addition to beating the base and not weakening permissions/approval).
    tuning_deploy_min_pass_rate: float = 0.9
    tuning_deploy_min_correctness: float = 0.9


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
