from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, TypeAdapter

from sysmind.agent.contracts import ToolDescriptor

RiskLevel: TypeAlias = Literal["read_only", "network", "state_change", "destructive"]
ConfirmationPolicy: TypeAlias = Literal["none", "each_time", "double"]
ToolHandler: TypeAlias = Callable[[BaseModel, Event], object]
ToolSummarizer: TypeAlias = Callable[[object], dict[str, object]]

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{2,79}$")
_VERSION_PATTERN = re.compile(r"^[1-9]\d*\.\d+$")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    version: str
    description: str
    input_model: type[BaseModel]
    output_adapter: TypeAdapter[Any]
    risk_level: RiskLevel
    required_privilege: str
    sensitivity: tuple[str, ...]
    timeout_seconds: float
    concurrency_key: str
    confirmation_policy: ConfirmationPolicy
    handler: ToolHandler
    summarizer: ToolSummarizer

    @property
    def qualified_name(self) -> str:
        return f"{self.name}@{self.version}"

    def descriptor(self) -> ToolDescriptor:
        return ToolDescriptor(
            name=self.name,
            version=self.version,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
            risk_level=self.risk_level,
            sensitivity=self.sensitivity,
        )


class ToolRegistryError(ValueError):
    pass


class ToolRegistry:
    def __init__(self, definitions: tuple[ToolDefinition, ...] = ()) -> None:
        self._definitions: dict[str, ToolDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ToolDefinition) -> None:
        if not _NAME_PATTERN.fullmatch(definition.name):
            raise ToolRegistryError(f"Invalid tool name: {definition.name}")
        if not _VERSION_PATTERN.fullmatch(definition.version):
            raise ToolRegistryError(f"Invalid tool version: {definition.version}")
        if not definition.description.strip():
            raise ToolRegistryError("Tool description must not be empty.")
        if not 0 < definition.timeout_seconds <= 60:
            raise ToolRegistryError("Tool timeout must be between 0 and 60 seconds.")
        if not callable(definition.handler) or not callable(definition.summarizer):
            raise ToolRegistryError("Tool handler and summarizer must be callable.")
        input_schema = definition.input_model.model_json_schema()
        output_schema = definition.output_adapter.json_schema()
        if input_schema.get("type") != "object" or not output_schema:
            raise ToolRegistryError("Tool schemas must be valid and non-empty.")
        if definition.qualified_name in self._definitions:
            raise ToolRegistryError(f"Duplicate tool: {definition.qualified_name}")
        self._definitions[definition.qualified_name] = definition

    def get(self, name: str, version: str) -> ToolDefinition | None:
        return self._definitions.get(f"{name}@{version}")

    def require(self, qualified_name: str) -> ToolDefinition:
        definition = self._definitions.get(qualified_name)
        if definition is None:
            raise ToolRegistryError(f"Unknown tool: {qualified_name}")
        return definition

    def descriptors(self, allowed: tuple[str, ...]) -> tuple[ToolDescriptor, ...]:
        return tuple(self.require(name).descriptor() for name in allowed)

    def available(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._definitions.values())
