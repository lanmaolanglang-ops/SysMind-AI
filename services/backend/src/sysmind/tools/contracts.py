from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    name: str
    version: str
    description: str
    input_schema: dict[str, object]
    risk_level: str
    sensitivity: tuple[str, ...]

    @property
    def qualified_name(self) -> str:
        return f"{self.name}@{self.version}"


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


class ToolPermissionError(RuntimeError):
    pass
