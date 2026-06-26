from __future__ import annotations

from app.services.ai.providers._compat_core import OpenAICompatCore
from app.services.ai.providers.base import CAPS_CONSERVATIVE, LLMProvider


class OpenAICompatibleProvider(OpenAICompatCore, LLMProvider):
    """Calls any backend that speaks ``POST /v1/chat/completions``.

    Works for OpenAI, OpenRouter, LM Studio, llama.cpp's server, and most
    Ollama deployments running the OpenAI shim. Beyond the legacy synchronous
    ``chat`` method it also offers async completions, streaming, tools and
    structured output (see :class:`OpenAICompatCore`) — but only advertises the
    features it is told the backend supports (default: conservative).
    """

    DEFAULT_CAPS = CAPS_CONSERVATIVE
    health_path = None  # generic OpenAI servers have no /health; probe /models
