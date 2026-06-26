#!/usr/bin/env python3
"""Mock OpenAI-compatible server — a TEST DOUBLE for the smoke/bench harness.

This is NOT vLLM and NOT a model. It implements just enough of the
OpenAI-compatible surface (``/health``, ``/v1/models``, ``/v1/chat/completions``
with streaming, tool calls and JSON-schema structured output) to let
``vllm-smoke.sh`` and ``vllm-bench.sh`` be validated OFFLINE, with no GPU and no
model download. Use it to prove the *harness* works; it tells you nothing about
a real model.

    python3 mock_vllm_server.py            # listens on 127.0.0.1:8000
    MOCK_API_KEY=test-key MOCK_REQUIRE_KEY=1 python3 mock_vllm_server.py

Env:
    MOCK_HOST (127.0.0.1), MOCK_PORT (8000),
    MOCK_SERVED_MODEL_NAME (supervoid-brain),
    MOCK_API_KEY (""), MOCK_REQUIRE_KEY (0).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVED = os.environ.get("MOCK_SERVED_MODEL_NAME", "supervoid-brain")
API_KEY = os.environ.get("MOCK_API_KEY", "")
REQUIRE_KEY = os.environ.get("MOCK_REQUIRE_KEY", "0").lower() in ("1", "true", "yes", "on")


def _synth_from_schema(schema: dict):
    """Produce a deterministic value satisfying a (subset of) JSON schema."""
    t = schema.get("type")
    if t == "object":
        props = schema.get("properties", {})
        return {k: _synth_from_schema(v) for k, v in props.items()}
    if t == "array":
        return [_synth_from_schema(schema.get("items", {"type": "string"}))]
    if t == "integer":
        return 2102650
    if t == "number":
        return 12.5
    if t == "boolean":
        return True
    # default: string
    return "Paris"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # quiet
        pass

    # --- helpers -----------------------------------------------------------
    def _request_id(self) -> str:
        return self.headers.get("X-Request-Id") or uuid.uuid4().hex

    def _auth_ok(self) -> bool:
        if not REQUIRE_KEY:
            return True
        got = self.headers.get("Authorization", "")
        return got == f"Bearer {API_KEY}"

    def _send_json(self, obj, code=200, rid=None):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if rid:
            self.send_header("X-Request-Id", rid)
        self.end_headers()
        self.wfile.write(data)

    # --- routes ------------------------------------------------------------
    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            body = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/v1/models"):
            rid = self._request_id()
            if not self._auth_ok():
                return self._send_json({"error": {"message": "unauthorized"}}, 401, rid)
            return self._send_json(
                {"object": "list", "data": [{"id": SERVED, "object": "model", "owned_by": "supervoid"}]},
                200, rid,
            )
        self._send_json({"error": {"message": "not found"}}, 404)

    def do_POST(self):
        rid = self._request_id()
        if not self.path.startswith("/v1/chat/completions"):
            return self._send_json({"error": {"message": "not found"}}, 404, rid)
        if not self._auth_ok():
            return self._send_json({"error": {"message": "unauthorized"}}, 401, rid)

        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._send_json({"error": {"message": "bad json"}}, 400, rid)

        model = req.get("model", SERVED)
        stream = bool(req.get("stream"))
        tools = req.get("tools")
        tool_choice = req.get("tool_choice", "auto")
        rfmt = req.get("response_format") or {}

        # Decide the assistant payload.
        tool_calls = None
        content = "pong"
        if tools and tool_choice != "none":
            fn = tools[0].get("function", {})
            params = (fn.get("parameters") or {}).get("properties", {})
            args = {k: _synth_from_schema(v) for k, v in params.items()}
            tool_calls = [{
                "id": "call_" + uuid.uuid4().hex[:8],
                "type": "function",
                "function": {"name": fn.get("name", "tool"), "arguments": json.dumps(args)},
            }]
            content = None
        elif rfmt.get("type") == "json_schema":
            schema = (rfmt.get("json_schema") or {}).get("schema", {})
            content = json.dumps(_synth_from_schema(schema))

        created = int(time.time())
        cid = "chatcmpl-" + uuid.uuid4().hex[:12]

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Request-Id", rid)
            self.send_header("Connection", "close")
            self.end_headers()

            def emit(delta, finish=None):
                chunk = {
                    "id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                }
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()

            emit({"role": "assistant"})
            for word in (content or "pong").split():
                emit({"content": word + " "})
            emit({}, finish="stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        message = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls
        self._send_json(
            {
                "id": cid, "object": "chat.completion", "created": created, "model": model,
                "choices": [{
                    "index": 0, "message": message,
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                }],
                "usage": {"prompt_tokens": 16, "completion_tokens": 8, "total_tokens": 24},
            },
            200, rid,
        )


def main():
    host = os.environ.get("MOCK_HOST", "127.0.0.1")
    port = int(os.environ.get("MOCK_PORT", "8000"))
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"[mock_vllm] TEST DOUBLE listening on http://{host}:{port} "
          f"(served='{SERVED}', require_key={REQUIRE_KEY})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
