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

    def __post_init__(self) -> None:
        # Keep the same bounds as ToolRegistry.register so toolset declarations
        # cannot drift above the runtime ceiling.
        if not 0 < self.timeout_seconds <= 60:
            raise ValueError("Tool timeout must be between 0 and 60 seconds.")


class ToolUnavailableError(RuntimeError):
    pass


class ToolCancelledError(RuntimeError):
    pass


class ToolPermissionError(RuntimeError):
    pass
