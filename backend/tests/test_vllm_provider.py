"""Mock-server tests for the async vLLM / OpenAI-compatible provider.

A small in-process HTTP server speaks just enough of the OpenAI surface to
exercise the provider over a real socket (no network egress). The async
methods are driven with ``asyncio.run`` so we need no pytest-asyncio plugin.

Covered: ordinary response, streaming, tool call, malformed tool call,
structured output, timeout, provider unavailable, request-id propagation —
plus retry-on-transient and capability gating.
"""
from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services.ai.providers import (
    CAPS_CONSERVATIVE,
    CapabilityError,
    ChatMessage,
    ChatRequest,
    OpenAICompatibleProvider,
    ProviderTimeoutError,
    ProviderUnavailableError,
    VLLMProvider,
)


# --- mock server -----------------------------------------------------------
class _State:
    def __init__(self) -> None:
        self.served_model = "supervoid-brain"
        self.sleep = 0.0
        self.status_sequence: list[int] = []  # consumed in order, then 200
        self.force_status: int | None = None
        self.malformed_tool = False
        self.calls = 0
        self.last_body: dict | None = None
        self.last_headers: dict | None = None


def _synth(schema: dict):
    t = schema.get("type")
    if t == "object":
        return {k: _synth(v) for k, v in (schema.get("properties") or {}).items()}
    if t == "integer":
        return 2102650
    if t == "number":
        return 1.5
    if t == "boolean":
        return True
    if t == "array":
        return [_synth(schema.get("items", {"type": "string"}))]
    return "Paris"


def _make_handler(state: _State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # silence
            pass

        def _rid(self) -> str:
            return self.headers.get("X-Request-Id") or "srv-" + str(state.calls)

        def _write_json(self, obj, code=200, rid=None):
            data = json.dumps(obj).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                if rid:
                    self.send_header("X-Request-Id", rid)
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path.rstrip("/") == "/health":
                try:
                    self.send_response(200)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"ok")
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            if self.path.startswith("/v1/models"):
                self._write_json(
                    {"object": "list",
                     "data": [{"id": state.served_model, "object": "model"}]},
                    rid=self._rid(),
                )
                return
            self._write_json({"error": "not found"}, 404)

        def do_POST(self):
            state.calls += 1
            rid = self._rid()
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                body = {}
            state.last_body = body
            state.last_headers = dict(self.headers)

            if state.sleep:
                time.sleep(state.sleep)

            # Forced / sequenced error statuses (for retry + no-retry tests).
            status = None
            if state.force_status is not None:
                status = state.force_status
            elif state.status_sequence:
                status = state.status_sequence.pop(0)
            if status is not None and status >= 400:
                self._write_json({"error": {"message": f"status {status}"}},
                                 code=status, rid=rid)
                return

            stream = bool(body.get("stream"))
            tools = body.get("tools")
            rfmt = body.get("response_format") or {}

            if stream:
                self._stream(body, rid)
                return

            if tools:
                args = "{bad json" if state.malformed_tool else json.dumps(
                    {"city": "Paris"})
                msg = {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "get_weather", "arguments": args},
                    }],
                }
                finish = "tool_calls"
            elif rfmt.get("type") == "json_schema":
                schema = (rfmt.get("json_schema") or {}).get("schema", {})
                msg = {"role": "assistant", "content": json.dumps(_synth(schema))}
                finish = "stop"
            else:
                msg = {"role": "assistant", "content": "pong"}
                finish = "stop"

            self._write_json(
                {
                    "id": "chatcmpl-x", "object": "chat.completion",
                    "model": body.get("model", state.served_model),
                    "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2,
                              "total_tokens": 7},
                },
                rid=rid,
            )

        def _stream(self, body, rid):
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.send_header("X-Request-Id", rid)
                self.end_headers()
                self.close_connection = True

                def emit(delta, finish=None):
                    chunk = {
                        "id": "chatcmpl-x", "object": "chat.completion.chunk",
                        "model": body.get("model", state.served_model),
                        "choices": [{"index": 0, "delta": delta,
                                     "finish_reason": finish}],
                    }
                    self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                    self.wfile.flush()

                emit({"role": "assistant"})
                for word in ("one ", "two ", "three"):
                    emit({"content": word})
                emit({}, finish="stop")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


@pytest.fixture()
def mock():
    state = _State()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}/v1"
    try:
        yield base_url, state
    finally:
        server.shutdown()
        server.server_close()


def _vllm(base_url: str, **kw) -> VLLMProvider:
    kw.setdefault("retry_backoff", 0.01)  # keep retry tests fast
    return VLLMProvider(
        name="vllm", base_url=base_url, default_model="supervoid-brain",
        api_key="test-key", **kw,
    )


def _complete(provider, request):
    async def _run():
        try:
            return await provider.acomplete(request)
        finally:
            await provider.aclose()
    return asyncio.run(_run())


def _collect(provider, request):
    async def _run():
        chunks = []
        try:
            async for ch in provider.astream(request):
                chunks.append(ch)
        finally:
            await provider.aclose()
        return chunks
    return asyncio.run(_run())


def _msgs():
    return [ChatMessage("user", "hi")]


# --- 1. ordinary response --------------------------------------------------
def test_ordinary_response(mock):
    base_url, state = mock
    p = _vllm(base_url)
    res = _complete(p, ChatRequest(messages=_msgs(), max_tokens=16))
    assert res.content == "pong"
    assert res.provider == "vllm"
    assert res.finish_reason == "stop"
    assert res.usage == {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
    assert res.latency_ms is not None and res.latency_ms >= 0
    assert state.calls == 1


# --- 2. streaming ----------------------------------------------------------
def test_streaming(mock):
    base_url, _ = mock
    p = _vllm(base_url)
    chunks = _collect(p, ChatRequest(messages=_msgs(), stream=True))
    text = "".join(c.content for c in chunks if c.content)
    assert text == "one two three"
    assert any(c.finish_reason == "stop" for c in chunks)
    assert all(c.request_id for c in chunks)


# --- 3. tool call ----------------------------------------------------------
def test_tool_call(mock):
    base_url, _ = mock
    p = _vllm(base_url)
    req = ChatRequest(
        messages=[ChatMessage("user", "weather in Paris?")],
        tools=[{"type": "function", "function": {
            "name": "get_weather",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string"}}}}}],
        tool_choice="auto",
    )
    res = _complete(p, req)
    assert res.finish_reason == "tool_calls"
    assert res.tool_calls and res.tool_calls[0].name == "get_weather"
    assert res.tool_calls[0].is_valid
    assert res.tool_calls[0].arguments_obj() == {"city": "Paris"}


# --- 4. malformed tool call ------------------------------------------------
def test_malformed_tool_call(mock):
    base_url, state = mock
    state.malformed_tool = True
    p = _vllm(base_url)
    req = ChatRequest(
        messages=_msgs(),
        tools=[{"type": "function", "function": {"name": "get_weather"}}],
    )
    res = _complete(p, req)
    # The provider surfaces the malformed call without crashing.
    assert res.tool_calls and res.tool_calls[0].name == "get_weather"
    assert res.tool_calls[0].is_valid is False
    assert res.tool_calls[0].arguments_obj() is None
    assert res.tool_calls[0].arguments == "{bad json"


# --- 5. structured output --------------------------------------------------
def test_structured_output(mock):
    base_url, state = mock
    p = _vllm(base_url)
    schema = {"type": "object",
              "properties": {"city": {"type": "string"},
                             "population": {"type": "integer"}},
              "required": ["city", "population"]}
    req = ChatRequest(
        messages=_msgs(),
        response_format={"type": "json_schema",
                         "json_schema": {"name": "city", "schema": schema}},
    )
    res = _complete(p, req)
    parsed = json.loads(res.content)
    assert parsed["city"] and isinstance(parsed["population"], int)
    # The request actually carried the structured-output directive.
    assert state.last_body["response_format"]["type"] == "json_schema"


def test_structured_output_rejected_when_unsupported(mock):
    base_url, state = mock
    # Generic conservative provider must NOT silently send unsupported features.
    p = OpenAICompatibleProvider(
        name="openai_compatible", base_url=base_url, default_model="m",
        capabilities=CAPS_CONSERVATIVE,
    )
    req = ChatRequest(
        messages=_msgs(),
        response_format={"type": "json_schema", "json_schema": {"schema": {}}},
    )
    with pytest.raises(CapabilityError):
        _complete(p, req)
    assert state.calls == 0  # never hit the wire


# --- 6. timeout ------------------------------------------------------------
def test_timeout(mock):
    base_url, state = mock
    state.sleep = 1.0
    p = _vllm(base_url, timeout=0.3, connect_timeout=0.3, max_retries=0)
    with pytest.raises(ProviderTimeoutError):
        _complete(p, ChatRequest(messages=_msgs()))


# --- 7. provider unavailable -----------------------------------------------
def test_provider_unavailable():
    # A port with nothing listening -> connection refused.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    p = _vllm(f"http://127.0.0.1:{port}/v1", max_retries=0, connect_timeout=0.5)
    with pytest.raises(ProviderUnavailableError):
        _complete(p, ChatRequest(messages=_msgs()))


# --- 8. request-id propagation ---------------------------------------------
def test_request_id_propagation(mock):
    base_url, state = mock
    p = _vllm(base_url)
    res = _complete(p, ChatRequest(messages=_msgs(), request_id="rid-xyz"))
    assert res.request_id == "rid-xyz"
    assert state.last_headers.get("X-Request-Id") == "rid-xyz"

    # When the caller doesn't supply one, the server-minted id is surfaced.
    res2 = _complete(_vllm(base_url), ChatRequest(messages=_msgs()))
    assert res2.request_id


# --- retries: transient 5xx retried, then succeeds -------------------------
def test_retries_transient_5xx_then_succeeds(mock):
    base_url, state = mock
    state.status_sequence = [503, 503]
    p = _vllm(base_url, max_retries=2)
    res = _complete(p, ChatRequest(messages=_msgs()))
    assert res.content == "pong"
    assert state.calls == 3  # two 503s + one success


def test_no_retry_on_client_error(mock):
    base_url, state = mock
    state.force_status = 400
    p = _vllm(base_url, max_retries=3)
    with pytest.raises(Exception):
        _complete(p, ChatRequest(messages=_msgs()))
    assert state.calls == 1  # 4xx is never retried


# --- health + capabilities -------------------------------------------------
def test_health_reports_reachable_and_model(mock):
    base_url, _ = mock
    p = _vllm(base_url)
    health = p.health()
    assert health.reachable is True
    assert health.model == "supervoid-brain"
    assert health.capabilities.tools and health.capabilities.json_schema
    assert health.detail is None


def test_capabilities_declared_per_provider(mock):
    base_url, _ = mock
    assert _vllm(base_url).capabilities().top_k is True
    generic = OpenAICompatibleProvider(
        name="openai_compatible", base_url=base_url, default_model="m")
    assert generic.capabilities().top_k is False
    assert generic.capabilities().tools is False
