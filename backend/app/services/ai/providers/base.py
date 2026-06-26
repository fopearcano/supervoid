from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional, Protocol, Sequence


# "tool" is added for tool-result turns; existing call-sites only use the
# first three, and ``as_openai`` stays backward compatible (see below).
ChatRole = Literal["system", "user", "assistant", "tool"]


@dataclass
class ChatMessage:
    role: ChatRole
    content: Optional[str] = None
    # Optional, only emitted when set (so plain messages serialise unchanged).
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict]] = None

    def as_openai(self) -> dict[str, Any]:
        # Plain system/user/assistant messages serialise to exactly
        # {"role", "content"} — preserving the historical wire shape.
        out: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            out["name"] = self.name
        if self.tool_call_id is not None:
            out["tool_call_id"] = self.tool_call_id
        if self.tool_calls is not None:
            out["tool_calls"] = self.tool_calls
        return out


@dataclass
class ToolCall:
    """A tool/function call returned by the model."""

    id: str
    name: str
    arguments: str  # raw JSON string exactly as the model produced it
    type: str = "function"
    index: Optional[int] = None

    def arguments_obj(self) -> Optional[dict]:
        """Parsed arguments, or ``None`` if the model emitted malformed JSON."""
        try:
            parsed = json.loads(self.arguments)
        except (json.JSONDecodeError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @property
    def is_valid(self) -> bool:
        return self.arguments_obj() is not None


@dataclass
class CompletionResult:
    content: str
    model: str
    provider: str
    usage: Optional[dict] = field(default=None)
    # --- additive, all optional so existing constructions stay valid ---
    finish_reason: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    reasoning: Optional[str] = None
    request_id: Optional[str] = None
    latency_ms: Optional[float] = None
    provider_metadata: Optional[dict] = None


@dataclass
class ChatChunk:
    """One streamed delta from a streaming chat completion."""

    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None
    request_id: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class ChatRequest:
    """A rich chat-completion request (superset of the legacy ``chat`` args).

    Only fields that are set are sent on the wire; unsupported features are
    rejected up front via the provider's declared capabilities rather than
    being blindly forwarded.
    """

    messages: Sequence[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None  # vLLM extension, sent via the request body
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[list[str]] = None
    tools: Optional[list[dict]] = None
    tool_choice: Optional[Any] = None
    response_format: Optional[dict] = None  # structured JSON-schema output
    reasoning: Optional[Any] = None  # passthrough when supplied
    stream: bool = False
    extra_body: Optional[dict] = None
    request_id: Optional[str] = None
    timeout: Optional[float] = None
    # Set False for any call tied to a committed side effect so the provider
    # never auto-retries it. Pure inference defaults to retry-on-transient.
    allow_retry: bool = True
    metadata: Optional[dict] = None


@dataclass
class ProviderCapabilities:
    """What an OpenAI-compatible backend actually supports.

    Defaults are conservative (everything off) so we never assume a feature
    is available; each provider declares what it can do.
    """

    streaming: bool = False
    tools: bool = False
    tool_choice: bool = False
    json_schema: bool = False
    reasoning: bool = False
    top_k: bool = False
    penalties: bool = False
    stop: bool = False
    model_listing: bool = False
    health: bool = False

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


# Capability presets ---------------------------------------------------------
# vLLM speaks the full surface we care about.
CAPS_VLLM = ProviderCapabilities(
    streaming=True, tools=True, tool_choice=True, json_schema=True,
    reasoning=True, top_k=True, penalties=True, stop=True,
    model_listing=True, health=True,
)
# Hosted OpenAI / OpenRouter: tools + structured output, but no top_k.
CAPS_OPENAI = ProviderCapabilities(
    streaming=True, tools=True, tool_choice=True, json_schema=True,
    reasoning=False, top_k=False, penalties=True, stop=True,
    model_listing=True, health=True,
)
# Generic / unknown OpenAI-compatible backend: assume only the basics.
CAPS_CONSERVATIVE = ProviderCapabilities(
    streaming=True, tools=False, tool_choice=False, json_schema=False,
    reasoning=False, top_k=False, penalties=True, stop=True,
    model_listing=True, health=True,
)
# Dry-run is offline: no network features, but it can "list" its stub model.
CAPS_DRYRUN = ProviderCapabilities(model_listing=True, health=True)


@dataclass
class ProviderHealth:
    """Health snapshot for the configured backend. Never carries secrets."""

    provider: str
    configured: bool
    reachable: bool
    model: Optional[str]
    capabilities: ProviderCapabilities
    latency_ms: Optional[float] = None
    detail: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "reachable": self.reachable,
            "model": self.model,
            "capabilities": self.capabilities.as_dict(),
            "latency_ms": self.latency_ms,
            "detail": self.detail,
        }


# --- exceptions -------------------------------------------------------------
class ProviderError(RuntimeError):
    """Base class for provider failures."""


class ProviderUnavailableError(ProviderError):
    """Backend could not be reached (connection refused / DNS / 5xx exhausted)."""


class ProviderTimeoutError(ProviderError):
    """Backend did not respond within the configured timeout."""


class CapabilityError(ProviderError):
    """A feature was requested that the configured provider does not support."""


# Subclasses ValueError so the historical ``chat`` contract (which raised
# ValueError on a malformed response) is preserved for existing callers/tests.
class MalformedResponseError(ProviderError, ValueError):
    """The backend returned a response we could not interpret."""


class LLMProvider(Protocol):
    """Anything that can answer a chat completion request.

    The synchronous ``chat`` method is the stable, legacy contract used by the
    editorial features. Richer, async capabilities (streaming, tools,
    structured output, health) are provided by concrete providers in addition
    to — never instead of — this method.
    """

    name: str

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        ...
