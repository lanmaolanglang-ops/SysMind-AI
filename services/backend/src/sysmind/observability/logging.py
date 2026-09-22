from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sysmind.security.redaction import is_sensitive_key, redact_text

_RESERVED_LOG_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}

def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if is_sensitive_key(key) else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        # Free-form strings can carry PII (user-profile paths, IPs, MACs) regardless
        # of the key they are nested under, so every string value is redacted.
        return redact_text(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "event_type": getattr(record, "event_type", "application_log"),
            "correlation_id": getattr(record, "correlation_id", None),
            "message": redact_text(record.getMessage()),
        }
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_KEYS
            and key not in {"component", "event_type", "correlation_id"}
        }
        if context:
            payload["context"] = _sanitize(context)
        if record.exc_info:
            # Tracebacks embed absolute file paths (with the account name) and the
            # exception text, both of which may contain PII. Clamp length so a huge
            # stack cannot flood the log stream (paths themselves are redacted below).
            payload["exception"] = redact_text(self.formatException(record.exc_info))[:4000]
        # default=str coerces non-JSON values through str(), which can leak object
        # reprs (paths, custom types carrying secrets) into the log stream. Prefer
        # JSON-safe context values at the call site.
        return json.dumps(_sanitize(payload), ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    component: str,
    event_type: str,
    correlation_id: str | None = None,
    **context: Any,
) -> None:
    # Filter reserved LogRecord keys on the write side so caller-supplied context
    # cannot collide with (or attempt to override) msg/args/levelname and friends.
    safe_context = {
        key: value
        for key, value in _sanitize(context).items()
        if key not in _RESERVED_LOG_KEYS
        and key not in {"component", "event_type", "correlation_id"}
    }
    logger.log(
        level,
        message,
        extra={
            "component": component,
            "event_type": event_type,
            # Correlation IDs come from an external header; clamp them so a hostile
            # value cannot inject arbitrarily long content into the JSON log stream.
            "correlation_id": _clamp_text(correlation_id),
            **safe_context,
        },
    )


def _clamp_text(value: str | None, limit: int = 64) -> str | None:
    if value is None:
        return None
    clamped = " ".join(value.split())
    return clamped[:limit]
