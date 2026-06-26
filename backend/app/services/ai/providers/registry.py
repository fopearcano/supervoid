from __future__ import annotations

from app.config import settings
from app.services.ai.providers.base import (
    CAPS_CONSERVATIVE,
    CAPS_OPENAI,
    LLMProvider,
)
from app.services.ai.providers.dry_run import DryRunProvider
from app.services.ai.providers.openai_compat import OpenAICompatibleProvider
from app.services.ai.providers.vllm import VLLMProvider


PROVIDER_DEFAULTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "lm_studio": "http://localhost:1234/v1",
    # ``openai_compatible`` is the catch-all for anything else; the
    # caller must supply AI_BASE_URL explicitly.
}

# Backends that advertise tools + structured output (but not top_k). Others
# fall back to the conservative capability set — we never assume a feature.
_RICH_OPENAI = {"openai", "openrouter"}

KNOWN_PROVIDERS = (
    "dry_run",
    *PROVIDER_DEFAULTS.keys(),
    "openai_compatible",
    "vllm",
)


_cache: dict[str, LLMProvider] = {}


def reset_provider_cache() -> None:
    """Clear the cached provider. Useful in tests."""
    _cache.clear()


def _build_provider() -> LLMProvider:
    kind = (settings.ai_provider or "dry_run").lower()

    if kind == "dry_run":
        return DryRunProvider()

    if kind == "vllm":
        if not settings.ai_base_url:
            raise ValueError(
                "AI provider 'vllm' requires AI_BASE_URL "
                "(e.g. http://vllm:8000/v1)."
            )
        return VLLMProvider(
            name="vllm",
            base_url=settings.ai_base_url,
            default_model=settings.ai_model,
            api_key=settings.ai_api_key,
            timeout=settings.ai_request_timeout,
            connect_timeout=settings.ai_connect_timeout,
            max_retries=settings.ai_max_retries,
        )

    if kind in PROVIDER_DEFAULTS or kind == "openai_compatible":
        base_url = settings.ai_base_url or PROVIDER_DEFAULTS.get(kind)
        if not base_url:
            raise ValueError(
                f"AI provider '{kind}' requires AI_BASE_URL to be set."
            )
        capabilities = CAPS_OPENAI if kind in _RICH_OPENAI else CAPS_CONSERVATIVE
        return OpenAICompatibleProvider(
            name=kind,
            base_url=base_url,
            default_model=settings.ai_model,
            api_key=settings.ai_api_key,
            timeout=settings.ai_request_timeout,
            connect_timeout=settings.ai_connect_timeout,
            max_retries=settings.ai_max_retries,
            capabilities=capabilities,
        )

    raise ValueError(
        f"Unknown AI provider: {kind!r}. "
        f"Expected one of: {', '.join(KNOWN_PROVIDERS)}."
    )


def get_provider() -> LLMProvider:
    """Return the configured provider, cached per process."""
    key = settings.ai_provider
    if key not in _cache:
        _cache[key] = _build_provider()
    return _cache[key]
