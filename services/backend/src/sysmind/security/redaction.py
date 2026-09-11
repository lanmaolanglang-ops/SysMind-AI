from __future__ import annotations

import re
from collections.abc import Mapping

SENSITIVE_KEYS = frozenset(
    {
        "access-token",
        "access_token",
        "authorization",
        "api-key",
        "api_key",
        "apikey",
        "auth",
        "credential",
        "key",
        "password",
        "private-key",
        "private_key",
        "pwd",
        "refresh-token",
        "refresh_token",
        "secret",
        "client-secret",
        "client_secret",
        "session-token",
        "session_token",
        "token",
    }
)

# Matches user-profile paths for drive letter (C:\Users\x, C:/Users/x) and UNC shares
# (\\server\Users\x); only the account segment is redacted so the remaining path
# structure stays readable. The segment class excludes whitespace and path separators
# so "…\Users\carol doc" redacts "carol" without swallowing the rest of the line.
_USER_PATH = re.compile(
    r"(?i)((?:\\\\[^\\\r\n]+|[A-Z]:)[/\\]Users[/\\])[^/\\\s]+"
)
_IPV4 = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
# Compressed or full IPv6 literals; a plain "12:34:56" time has no "::" and fewer than
# eight groups, so timestamps are not redacted by accident.
_IPV6 = re.compile(
    r"(?i)(?<![\w:.])"
    r"(?:[0-9A-F]{1,4}:){7}[0-9A-F]{1,4}"
    r"|(?:[0-9A-F]{1,4}:){1,7}:(?:[0-9A-F]{1,4}(?::[0-9A-F]{1,4}){0,6})?"
    r"|::(?:[0-9A-F]{1,4}(?::[0-9A-F]{1,4}){0,6})?"
    r"(?![\w:])"
)
_MAC = re.compile(r"(?i)\b(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}\b")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")


def is_sensitive_key(value: object) -> bool:
    normalized = str(value).strip().casefold()
    return normalized in SENSITIVE_KEYS or normalized.replace("-", "_") in SENSITIVE_KEYS


# Argument keys that carry an executable command line or shell/script payload. Values under
# these keys are always replaced in the audit trail, whatever the exact spelling.
COMMAND_ARGUMENT_KEYS = frozenset(
    {
        "cmd",
        "command",
        "command_line",
        "commandline",
        "executable",
        "executable_path",
        "powershell",
        "script",
        "script_path",
        "shell",
    }
)


def redact_arguments(arguments: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of tool arguments safe to persist in the audit trail.

    Secret-looking keys (via :func:`is_sensitive_key`) and command/shell payloads are
    replaced with a placeholder. Callers must pass the result — never the raw arguments —
    to any repository or log sink.
    """
    return {
        key: "[REDACTED]"
        if is_sensitive_key(key) or key.casefold().replace("-", "_") in COMMAND_ARGUMENT_KEYS
        else value
        for key, value in arguments.items()
    }


def redact_text(value: str) -> str:
    redacted = _USER_PATH.sub(r"\1[REDACTED]", value)
    redacted = _IPV4.sub(
        lambda match: (
            "[IP_REDACTED]"
            if all(0 <= int(part) <= 255 for part in match.group(0).split("."))
            else match.group(0)
        ),
        redacted,
    )
    redacted = _IPV6.sub("[IP_REDACTED]", redacted)
    redacted = _MAC.sub("[MAC_REDACTED]", redacted)
    return _EMAIL.sub("[EMAIL_REDACTED]", redacted)
