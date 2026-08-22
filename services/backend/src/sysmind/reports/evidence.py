from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

_PATH = re.compile(r"^\$(?:(?:\.[A-Za-z_][A-Za-z0-9_]*)|(?:\[(?:0|[1-9]\d*)\]))*$")
_TOKEN = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(0|[1-9]\d*)\]")


def evidence_path_exists(value: object, path: str) -> bool:
    """Resolve the project's non-executable JSONPath subset and require a real field."""
    if not _PATH.fullmatch(path):
        return False
    current = value
    for match in _TOKEN.finditer(path):
        key, index = match.groups()
        if key is not None:
            if not isinstance(current, Mapping) or key not in current:
                return False
            current = current[key]
        else:
            if (
                not isinstance(current, Sequence)
                or isinstance(current, (str, bytes, bytearray))
                or int(index) >= len(current)
            ):
                return False
            current = current[int(index)]
    return True
