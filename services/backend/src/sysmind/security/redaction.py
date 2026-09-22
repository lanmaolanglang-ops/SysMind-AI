from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

SENSITIVE_KEYS = frozenset(
    {
        "access-token",
        "access_token",
        "authorization",
        "api-key",
        "api_key",
        "apikey",
        "auth",
        "aws_secret_access_key",
        "aws-secret-access-key",
        "bearer",
        "connection_string",
        "connection-string",
        "credential",
        "csrf",
        "csrf_token",
        "id_token",
        "id-token",
        "key",
        "passphrase",
        "passwd",
        "password",
        "private-key",
        "private_key",
        "privatekey",
        "pwd",
        "refresh-token",
        "refresh_token",
        "secret",
        "client-secret",
        "client_secret",
        "secret_key",
        "secret-key",
        "session-token",
        "session_token",
        "set-cookie",
        "set_cookie",
        "cookie",
        "token",
        "x-api-key",
        "x_api_key",
        "xsrf",
        "xsrf_token",
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

# PEM private key blocks (PKCS#1/PKCS#8/SEC1/OpenSSH). Matched before line-oriented
# patterns so multi-line key material is replaced as one unit.
_PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN[ A-Z]*PRIVATE KEY-----[\s\S]*?-----END[ A-Z]*PRIVATE KEY-----"
)
# Compact JWS/JWT form: three base64url segments. Requires the characteristic "eyJ"
# header prefix so ordinary dotted identifiers are left alone.
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*")
# key=value / key: value credential assignments, including quoted values so
# api_key="a b c" is fully masked. Keys are the usual secret spellings.
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b("
    r"api[_-]?key|apikey|password|passwd|pwd|passphrase|secret|token|"
    r"auth[_-]?token|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"session[_-]?token|id[_-]?token|connection[_-]?string|private[_-]?key|"
    r"secret[_-]?key|aws[_-]?secret[_-]?access[_-]?key|csrf|xsrf|credential"
    r")\b(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)


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


def _is_command_argument_key(key: object) -> bool:
    return str(key).casefold().replace("-", "_") in COMMAND_ARGUMENT_KEYS


def redact_secrets(value: str) -> str:
    """Mask credential-looking material without touching paths/IPs/emails.

    Covers PEM private key blocks, JWT-like strings, Authorization Bearer tokens,
    and ``name=value`` / ``name: value`` assignments for common secret key names.
    Used standalone when a value must stay structurally intact (e.g. a Run command
    line that will be restored) but must not persist plaintext secrets.
    """
    redacted = _PEM_PRIVATE_KEY.sub("[PRIVATE_KEY_REDACTED]", value)
    redacted = _JWT.sub("[TOKEN_REDACTED]", redacted)
    redacted = _BEARER.sub(r"\1 [TOKEN_REDACTED]", redacted)
    return _CREDENTIAL_ASSIGNMENT.sub(r"\1\2[REDACTED]", redacted)


def redact_text(value: str) -> str:
    redacted = redact_secrets(value)
    redacted = _USER_PATH.sub(r"\1[REDACTED]", redacted)
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


def redact_structure(value: object) -> object:
    """Recursively redact nested dicts/lists for audit trails and provider payloads.

    Secret-looking and command-payload keys are replaced at every depth; free-form
    strings are passed through :func:`redact_text`. Non-string leaves are preserved
    so numeric evidence and JSON export stay intact.
    """
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            name = str(key)
            if is_sensitive_key(name) or _is_command_argument_key(name):
                result[name] = "[REDACTED]"
            else:
                result[name] = redact_structure(item)
        return result
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_structure(item) for item in value]
    return value


def redact_arguments(arguments: Mapping[str, object]) -> dict[str, object]:
    """Return a copy of tool arguments safe to persist in the audit trail.

    Secret-looking keys (via :func:`is_sensitive_key`) and command/shell payloads are
    replaced with a placeholder at any nesting depth. Callers must pass the result —
    never the raw arguments — to any repository or log sink.
    """
    return redact_structure(arguments)  # type: ignore[return-value]
