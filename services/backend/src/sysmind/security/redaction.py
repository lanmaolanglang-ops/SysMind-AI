from __future__ import annotations

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "api-key",
        "api_key",
        "apikey",
        "key",
        "password",
        "secret",
        "session-token",
        "session_token",
        "token",
    }
)


def is_sensitive_key(value: object) -> bool:
    normalized = str(value).strip().casefold()
    return normalized in SENSITIVE_KEYS or normalized.replace("-", "_") in SENSITIVE_KEYS
