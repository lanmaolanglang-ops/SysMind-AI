from __future__ import annotations

import re

_USER_PATH = re.compile(r"(?i)([A-Z]:\\Users\\)[^\\\s]+")
_IPV4 = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")


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
    return _EMAIL.sub("[EMAIL_REDACTED]", redacted)
