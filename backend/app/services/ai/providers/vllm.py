from __future__ import annotations

from app.services.ai.providers._compat_core import OpenAICompatCore
from app.services.ai.providers.base import CAPS_VLLM, LLMProvider


class VLLMProvider(OpenAICompatCore, LLMProvider):
    """A dedicated provider for a self-hosted vLLM OpenAI-compatible server.

    vLLM speaks the full surface SUPERVOID cares about — streaming, tool calls,
    structured JSON-schema output, reasoning fields, ``top_k`` (via the request
    body), penalties, stop sequences, ``/v1/models`` and a dedicated
    ``/health`` endpoint — so it declares the full capability set. It otherwise
    reuses the shared OpenAI-compatible core (async pool, retries, request-id
    propagation, cancellation/timeout).

    Base URL is the OpenAI-compatible root, e.g. ``http://vllm:8000/v1``; the
    unauthenticated ``/health`` probe is derived by stripping the ``/v1``.
    """

    DEFAULT_CAPS = CAPS_VLLM
    health_path = "/health"
