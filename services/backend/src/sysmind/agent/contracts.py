from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, TypeAlias

ProviderActionType: TypeAlias = Literal[
    "request_tool_calls", "ask_user", "propose_action", "finalize", "abort"
]


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
class ProviderToolCall:
    id: str
    name: str
    version: str
    arguments: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProviderAction:
    type: ProviderActionType
    content: str | None = None
    tool_calls: tuple[ProviderToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    system_prompt: str
    user_goal: str
    tools: tuple[ToolDescriptor, ...]
    messages: tuple[dict[str, object], ...] = ()
    max_output_tokens: int = 800


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    action: ProviderAction
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    provider_request_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class AgentProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def complete(self, request: ProviderRequest) -> ProviderResponse: ...


class ProviderError(RuntimeError):
    code = "provider_error"


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limited"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderProtocolError(ProviderError):
    code = "provider_protocol_error"


class ProviderTransportError(ProviderError):
    code = "provider_transport_error"
