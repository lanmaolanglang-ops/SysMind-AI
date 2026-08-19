from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    version: str
    timeout_seconds: float
    read_only: bool = True


class ToolUnavailableError(RuntimeError):
    pass


class ToolCancelledError(RuntimeError):
    pass

