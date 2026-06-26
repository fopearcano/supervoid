"""Shared core for OpenAI-compatible providers (generic + vLLM).

Provides, on top of the legacy synchronous ``chat`` contract:

* async chat completions over a reusable connection pool,
* streaming chat completions,
* tools / tool-choice / returned tool calls,
* structured JSON-schema output,
* reasoning / stop / top_p / top_k / presence + frequency penalties,
* request-id propagation, cancellation + timeout,
* model listing and health checks,
* capability gating (we never send a feature the backend doesn't declare),
* bounded retries for *safe transient* failures only.

The synchronous ``chat`` method is preserved byte-for-byte in behaviour so the
existing editorial features and their tests keep working unchanged.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator, Optional, Sequence

import httpx

from app.services.ai.providers.base import (
    CAPS_CONSERVATIVE,
    CapabilityError,
    ChatChunk,
    ChatMessage,
    ChatRequest,
    CompletionResult,
    MalformedResponseError,
    ProviderCapabilities,
    ProviderHealth,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ToolCall,
)

# Transient 5xx we will retry. 501/505 are not transient and are excluded.
DEFAULT_RETRY_STATUSES = frozenset({500, 502, 503, 504})

_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)
_TIMEOUT_ERRORS = (
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.TimeoutException,
)


class OpenAICompatCore:
    """Base implementation behind ``OpenAICompatibleProvider`` and ``VLLMProvider``."""

    # Subclasses override these.
    DEFAULT_CAPS: ProviderCapabilities = CAPS_CONSERVATIVE
    health_path: Optional[str] = None  # e.g. "/health" for vLLM

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        default_model: str,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        connect_timeout: float = 10.0,
        capabilities: Optional[ProviderCapabilities] = None,
        retry_statuses: frozenset[int] = DEFAULT_RETRY_STATUSES,
        retry_backoff: float = 0.25,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.api_key = api_key
        self.timeout = float(timeout)
        self.max_retries = max(0, int(max_retries))
        self.connect_timeout = float(connect_timeout)
        self._capabilities = capabilities or self.DEFAULT_CAPS
        self.retry_statuses = frozenset(retry_statuses)
        self.retry_backoff = float(retry_backoff)
        # Reusable async client, recreated if the running event loop changes
        # (so repeated ``asyncio.run`` calls in tests stay correct while
        # production — one loop — reuses a single pooled client).
        self._aclient: Optional[httpx.AsyncClient] = None
        self._aclient_loop: Optional[asyncio.AbstractEventLoop] = None

    # -- introspection -------------------------------------------------------
    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    @property
    def _server_root(self) -> str:
        """Backend root (without the trailing ``/v1``), for ``/health`` etc."""
        if self.base_url.endswith("/v1"):
            return self.base_url[:-3]
        return self.base_url

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _headers(
        self, request_id: Optional[str] = None, stream: bool = False
    ) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if request_id:
            headers["X-Request-Id"] = request_id
        if stream:
            headers["Accept"] = "text/event-stream"
        return headers

    # -- legacy synchronous contract (unchanged behaviour) -------------------
    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        headers = self._headers()
        body: dict[str, object] = {
            "model": model or self.default_model,
            "messages": [m.as_openai() for m in messages],
        }
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ValueError(
                f"Unexpected response shape from {self.name}: {data!r}"
            ) from exc

        return CompletionResult(
            content=content,
            model=str(data.get("model", body["model"])),
            provider=self.name,
            usage=data.get("usage"),
        )

    # -- request building / capability gating --------------------------------
    def _require(self, ok: bool, feature: str) -> None:
        if not ok:
            raise CapabilityError(
                f"Provider '{self.name}' does not support {feature}."
            )

    def _build_body(self, request: ChatRequest, *, stream: bool) -> dict:
        caps = self._capabilities
        body: dict[str, object] = {
            "model": request.model or self.default_model,
            "messages": [m.as_openai() for m in request.messages],
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.stop is not None:
            self._require(caps.stop, "stop sequences")
            body["stop"] = request.stop
        if request.presence_penalty is not None:
            self._require(caps.penalties, "presence_penalty")
            body["presence_penalty"] = request.presence_penalty
        if request.frequency_penalty is not None:
            self._require(caps.penalties, "frequency_penalty")
            body["frequency_penalty"] = request.frequency_penalty
        if request.tools is not None:
            self._require(caps.tools, "tool definitions")
            body["tools"] = request.tools
        if request.tool_choice is not None:
            self._require(caps.tool_choice, "tool_choice")
            body["tool_choice"] = request.tool_choice
        if request.response_format is not None:
            self._require(caps.json_schema, "structured JSON-schema output")
            body["response_format"] = request.response_format
        if request.reasoning is not None:
            self._require(caps.reasoning, "reasoning")
            body["reasoning"] = request.reasoning
        if request.top_k is not None:
            self._require(caps.top_k, "top_k")
            body["top_k"] = request.top_k  # vLLM extension (extra body field)
        if stream:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        # Escape hatch: caller-supplied extra body wins, last.
        if request.extra_body:
            body.update(request.extra_body)
        return body

    # -- response parsing ----------------------------------------------------
    @staticmethod
    def _parse_tool_calls(raw: Optional[list]) -> Optional[list[ToolCall]]:
        if not raw:
            return None
        calls: list[ToolCall] = []
        for i, tc in enumerate(raw):
            fn = (tc or {}).get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, (dict, list)):
                args = json.dumps(args)
            calls.append(
                ToolCall(
                    id=str(tc.get("id") or f"call_{i}"),
                    name=str(fn.get("name") or ""),
                    arguments=args if isinstance(args, str) else "",
                    type=str(tc.get("type") or "function"),
                    index=tc.get("index", i),
                )
            )
        return calls or None

    def _parse_completion(
        self, data: dict, latency_ms: float, request_id: Optional[str]
    ) -> CompletionResult:
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MalformedResponseError(
                f"Unexpected response shape from {self.name}: {data!r}"
            ) from exc
        content = message.get("content")
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        return CompletionResult(
            content=content if content is not None else "",
            model=str(data.get("model", self.default_model)),
            provider=self.name,
            usage=data.get("usage"),
            finish_reason=choice.get("finish_reason"),
            tool_calls=self._parse_tool_calls(message.get("tool_calls")),
            reasoning=reasoning,
            request_id=request_id or data.get("id"),
            latency_ms=round(latency_ms, 2),
            provider_metadata={
                "id": data.get("id"),
                "object": data.get("object"),
                "system_fingerprint": data.get("system_fingerprint"),
            },
        )

    def _parse_chunk(self, chunk: dict, request_id: Optional[str]) -> ChatChunk:
        choices = chunk.get("choices") or []
        delta = (choices[0].get("delta") if choices else {}) or {}
        finish = choices[0].get("finish_reason") if choices else None
        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        return ChatChunk(
            content=delta.get("content"),
            reasoning=reasoning,
            tool_calls=self._parse_tool_calls(delta.get("tool_calls")),
            finish_reason=finish,
            usage=chunk.get("usage"),
            request_id=request_id or chunk.get("id"),
            raw=chunk,
        )

    # -- async HTTP (reusable pool) ------------------------------------------
    def _client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if (
            self._aclient is None
            or self._aclient.is_closed
            or self._aclient_loop is not loop
        ):
            limits = httpx.Limits(
                max_connections=32, max_keepalive_connections=16
            )
            timeout = httpx.Timeout(self.timeout, connect=self.connect_timeout)
            self._aclient = httpx.AsyncClient(limits=limits, timeout=timeout)
            self._aclient_loop = loop
        return self._aclient

    async def aclose(self) -> None:
        if self._aclient is not None and not self._aclient.is_closed:
            try:
                await self._aclient.aclose()
            except RuntimeError:
                pass  # event loop already closing
        self._aclient = None
        self._aclient_loop = None

    async def _backoff(self, attempt: int) -> None:
        await asyncio.sleep(self.retry_backoff * (2 ** attempt))

    async def _post_with_retry(
        self,
        url: str,
        headers: dict[str, str],
        body: dict,
        timeout: Optional[float],
        allow_retry: bool,
    ) -> httpx.Response:
        """POST with bounded retries for SAFE transient failures only.

        Retries connection failures, timeouts, and selected 5xx. Never retries
        a 4xx, never retries a 2xx (a successful, completed call). The caller
        sets ``allow_retry=False`` for anything tied to a side effect.
        """
        attempt = 0
        while True:
            try:
                response = await self._client().post(
                    url, headers=headers, json=body, timeout=timeout
                )
            except _CONNECT_ERRORS as exc:
                if allow_retry and attempt < self.max_retries:
                    await self._backoff(attempt)
                    attempt += 1
                    continue
                raise ProviderUnavailableError(
                    f"{self.name} unreachable: {exc!r}"
                ) from exc
            except _TIMEOUT_ERRORS as exc:
                if allow_retry and attempt < self.max_retries:
                    await self._backoff(attempt)
                    attempt += 1
                    continue
                raise ProviderTimeoutError(
                    f"{self.name} timed out after {self.timeout}s"
                ) from exc

            if (
                response.status_code in self.retry_statuses
                and allow_retry
                and attempt < self.max_retries
            ):
                await self._backoff(attempt)
                attempt += 1
                continue
            return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code in self.retry_statuses:
            raise ProviderUnavailableError(
                f"{self.name} returned HTTP {response.status_code} (after retries)"
            )
        # Other 4xx/5xx: not transient — surface, no retry. Body is the
        # provider's error payload (never our API key).
        raise MalformedResponseError(
            f"{self.name} returned HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

    async def acomplete(self, request: ChatRequest) -> CompletionResult:
        body = self._build_body(request, stream=False)
        headers = self._headers(request.request_id)
        timeout = request.timeout or self.timeout
        started = time.perf_counter()
        response = await self._post_with_retry(
            self._url("chat/completions"),
            headers,
            body,
            timeout,
            request.allow_retry,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if response.status_code >= 400:
            self._raise_for_status(response)
        data = response.json()
        request_id = response.headers.get("x-request-id") or request.request_id
        return self._parse_completion(data, latency_ms, request_id)

    async def astream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        """Stream a chat completion. No auto-retry once bytes have started —
        a half-streamed completion must never be silently regenerated."""
        self._require(self._capabilities.streaming, "streaming")
        body = self._build_body(request, stream=True)
        headers = self._headers(request.request_id, stream=True)
        timeout = request.timeout or self.timeout
        try:
            async with self._client().stream(
                "POST",
                self._url("chat/completions"),
                headers=headers,
                json=body,
                timeout=timeout,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    self._raise_for_status(response)
                request_id = (
                    response.headers.get("x-request-id") or request.request_id
                )
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    yield self._parse_chunk(chunk, request_id)
        except _CONNECT_ERRORS as exc:
            raise ProviderUnavailableError(
                f"{self.name} unreachable: {exc!r}"
            ) from exc
        except _TIMEOUT_ERRORS as exc:
            raise ProviderTimeoutError(
                f"{self.name} timed out after {self.timeout}s"
            ) from exc

    # -- model listing -------------------------------------------------------
    async def alist_models(self) -> list[str]:
        self._require(self._capabilities.model_listing, "model listing")
        response = await self._post_with_retry_get(
            self._url("models"), self._headers(), self.timeout, allow_retry=True
        )
        if response.status_code >= 400:
            self._raise_for_status(response)
        data = response.json()
        return [str(m.get("id")) for m in data.get("data", []) if m.get("id")]

    def list_models(self) -> list[str]:
        with httpx.Client(
            timeout=httpx.Timeout(self.timeout, connect=self.connect_timeout)
        ) as client:
            response = client.get(self._url("models"), headers=self._headers())
            response.raise_for_status()
            data = response.json()
        return [str(m.get("id")) for m in data.get("data", []) if m.get("id")]

    async def _post_with_retry_get(
        self,
        url: str,
        headers: dict[str, str],
        timeout: Optional[float],
        allow_retry: bool,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                response = await self._client().get(
                    url, headers=headers, timeout=timeout
                )
            except _CONNECT_ERRORS as exc:
                if allow_retry and attempt < self.max_retries:
                    await self._backoff(attempt)
                    attempt += 1
                    continue
                raise ProviderUnavailableError(
                    f"{self.name} unreachable: {exc!r}"
                ) from exc
            except _TIMEOUT_ERRORS as exc:
                if allow_retry and attempt < self.max_retries:
                    await self._backoff(attempt)
                    attempt += 1
                    continue
                raise ProviderTimeoutError(
                    f"{self.name} timed out after {self.timeout}s"
                ) from exc
            if (
                response.status_code in self.retry_statuses
                and allow_retry
                and attempt < self.max_retries
            ):
                await self._backoff(attempt)
                attempt += 1
                continue
            return response

    # -- health --------------------------------------------------------------
    def health(self) -> ProviderHealth:
        """Synchronous health probe. Never returns or logs the API key."""
        started = time.perf_counter()
        reachable = False
        model: Optional[str] = None
        detail: Optional[str] = None
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self.timeout, connect=self.connect_timeout)
            ) as client:
                if self.health_path:
                    resp = client.get(
                        f"{self._server_root}{self.health_path}",
                        headers=self._headers(),
                    )
                    reachable = resp.status_code < 500
                # Resolve the active model (and use it as the reachability
                # probe when there is no dedicated health path).
                try:
                    models_resp = client.get(
                        self._url("models"), headers=self._headers()
                    )
                    if models_resp.status_code < 400:
                        ids = [
                            m.get("id")
                            for m in models_resp.json().get("data", [])
                            if m.get("id")
                        ]
                        if not self.health_path:
                            reachable = True
                        if self.default_model in ids:
                            model = self.default_model
                        elif ids:
                            model = ids[0]
                except (httpx.HTTPError,) as exc:
                    if not self.health_path:
                        detail = f"models probe failed: {exc.__class__.__name__}"
        except _CONNECT_ERRORS as exc:
            detail = f"unreachable: {exc.__class__.__name__}"
        except _TIMEOUT_ERRORS as exc:
            detail = f"timeout: {exc.__class__.__name__}"
        except httpx.HTTPError as exc:
            detail = f"error: {exc.__class__.__name__}"
        latency = (time.perf_counter() - started) * 1000.0
        return ProviderHealth(
            provider=self.name,
            configured=True,
            reachable=reachable,
            model=model or self.default_model,
            capabilities=self._capabilities,
            latency_ms=round(latency, 2),
            detail=detail,
        )

    async def ahealth(self) -> ProviderHealth:
        started = time.perf_counter()
        reachable = False
        model: Optional[str] = None
        detail: Optional[str] = None
        try:
            if self.health_path:
                resp = await self._client().get(
                    f"{self._server_root}{self.health_path}",
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                reachable = resp.status_code < 500
            models_resp = await self._client().get(
                self._url("models"), headers=self._headers(), timeout=self.timeout
            )
            if models_resp.status_code < 400:
                ids = [
                    m.get("id")
                    for m in models_resp.json().get("data", [])
                    if m.get("id")
                ]
                if not self.health_path:
                    reachable = True
                if self.default_model in ids:
                    model = self.default_model
                elif ids:
                    model = ids[0]
        except _CONNECT_ERRORS as exc:
            detail = f"unreachable: {exc.__class__.__name__}"
        except _TIMEOUT_ERRORS as exc:
            detail = f"timeout: {exc.__class__.__name__}"
        except httpx.HTTPError as exc:
            detail = f"error: {exc.__class__.__name__}"
        latency = (time.perf_counter() - started) * 1000.0
        return ProviderHealth(
            provider=self.name,
            configured=True,
            reachable=reachable,
            model=model or self.default_model,
            capabilities=self._capabilities,
            latency_ms=round(latency, 2),
            detail=detail,
        )
