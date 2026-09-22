from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

AgentTaskStatus: TypeAlias = Literal[
    "created",
    "planning",
    "running_tools",
    "analyzing",
    "waiting_user_input",
    "completed",
    "cancelling",
    "cancelled",
    "failed",
    "timed_out",
    "interrupted",
]
AgentEventType: TypeAlias = Literal[
    "task.created",
    "task.status",
    "provider.started",
    "provider.completed",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "task.message",
    "task.completed",
    "task.failed",
]


@dataclass(frozen=True, slots=True)
class AgentBudget:
    max_rounds: int = 4
    max_tool_calls: int = 8
    timeout_seconds: float = 30.0
    max_parallel_tools: int = 2

    def __post_init__(self) -> None:
        # Mirrors AgentTaskManager.start so an invalid budget fails at construction,
        # not halfway through wiring a task.
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be at least 1.")
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be at least 1.")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_parallel_tools < 1:
            raise ValueError("max_parallel_tools must be at least 1.")


@dataclass(frozen=True, slots=True)
class AgentTaskRecord:
    id: str
    status: AgentTaskStatus
    user_goal: str
    provider: str
    allowed_tools: tuple[str, ...]
    budget: AgentBudget
    current_round: int
    tool_call_count: int
    progress: int
    working_summary: dict[str, object]
    final_output: str | None
    failure_code: str | None
    failure_message: str | None
    cancel_requested: bool
    created_at: str
    started_at: str | None
    finished_at: str | None
    schema_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "working_summary", dict(self.working_summary))


@dataclass(frozen=True, slots=True)
class AgentTaskEvent:
    id: int
    task_id: str
    event_type: AgentEventType
    data: dict[str, object]
    created_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", dict(self.data))


@dataclass(frozen=True, slots=True)
class AgentToolCallRecord:
    id: str
    task_id: str
    provider_call_id: str
    tool_name: str
    tool_version: str
    status: str
    arguments_hash: str
    risk_level: str
    started_at: str
    finished_at: str | None
    duration_ms: int | None
    result_summary: dict[str, object] | None
    error_code: str | None
    error_message: str | None

    def __post_init__(self) -> None:
        if self.result_summary is not None:
            object.__setattr__(self, "result_summary", dict(self.result_summary))
