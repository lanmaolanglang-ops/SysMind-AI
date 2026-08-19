from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

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

_SENSITIVE_KEYS = {"authorization", "api_key", "apikey", "session_token", "token"}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "event_type": getattr(record, "event_type", "application_log"),
            "correlation_id": getattr(record, "correlation_id", None),
            "message": record.getMessage(),
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
            payload["exception"] = self.formatException(record.exc_info)
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
    logger.log(
        level,
        message,
        extra={
            "component": component,
            "event_type": event_type,
            "correlation_id": correlation_id,
            **_sanitize(context),
        },
    )
