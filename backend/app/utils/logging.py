"""Process logging configuration.

A small wrapper around the stdlib so the app and uvicorn share one
formatter and so the request-id middleware can stamp every line with a
correlation id.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from typing import Any, Optional

from app.config import settings


# A ContextVar lets every log call inside a single request pick up the
# correlation id without having to thread it through every function.
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(value: Optional[str]) -> None:
    _request_id_var.set(value)


def get_request_id() -> Optional[str]:
    return _request_id_var.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


_DEFAULT_FORMAT = (
    "%(asctime)s [%(levelname)-5s] %(name)s rid=%(request_id)s %(message)s"
)


def configure_logging(level: Optional[str] = None) -> None:
    """Idempotent root logger setup.

    Honours `LOG_LEVEL` from settings; quiets uvicorn's per-request access
    log so our middleware-based access line is the canonical record.
    """
    resolved = (level or settings.log_level).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    handler.addFilter(_RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)

    # Keep our own loggers at the configured level…
    logging.getLogger("app").setLevel(resolved)
    # …and quiet uvicorn's own access log; we emit our own.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# === structured, redacted event logging (Prompt 16) ========================
# Keys whose VALUE must never be logged: credentials, private prompts, and
# contract-sensitive content. Boundary logs never carry prompt/response bodies
# in the first place; this is defence-in-depth for any stray field.
_REDACT_KEY_RE = re.compile(
    r"(token|secret|password|passwd|authorization|bearer|credential|api[_-]?key|"
    r"private|prompt|contract|terms)",
    re.IGNORECASE,
)
_REDACTED = "[redacted]"
_MAX_LOG_VALUE = 200

_ops_logger = logging.getLogger("supervoid.ops")


def redact_log(value: Any) -> Any:
    """Recursively redact secret-/private-/contract-keyed fields and cap long
    strings, for safe structured logging."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            out[str(key)] = _REDACTED if _REDACT_KEY_RE.search(str(key)) else redact_log(val)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_log(v) for v in value]
    if isinstance(value, str) and len(value) > _MAX_LOG_VALUE:
        return value[:_MAX_LOG_VALUE] + "…"
    return value


def log_event(event: str, **fields: Any) -> None:
    """Emit one structured, redacted log line for a correlated boundary (model
    request, MCP tool call, agent run, proposal execution). The formatter already
    stamps the timestamp + correlation id (``rid=…``); we never log prompt or
    response bodies — only ids, counts and timings."""
    try:
        payload = json.dumps(redact_log(fields), default=str, sort_keys=True)
    except Exception:  # noqa: BLE001 - logging must never raise
        payload = "{}"
    _ops_logger.info("event=%s %s", event, payload)
