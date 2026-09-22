from __future__ import annotations

import hashlib


def opaque_item_id(*parts: object) -> str:
    """Build a stable, non-reversible identifier for Windows evidence items."""

    return hashlib.sha256("\0".join(str(part) for part in parts).encode()).hexdigest()


def process_item_id(pid: int, created_at: float) -> str:
    """Bind process evidence to one PID incarnation rather than the PID alone."""

    # FILETIME and psutil timestamps can differ below the millisecond. The action
    # adapter uses the same rounding before comparing an opened process handle.
    return opaque_item_id("current_user_process", pid, round(float(created_at), 2))


def startup_item_id(source_kind: str, name: str) -> str:
    """Bind startup evidence to one application-owned source/name pair."""

    return opaque_item_id(source_kind, name)
