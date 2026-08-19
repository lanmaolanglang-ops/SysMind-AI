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


@dataclass(frozen=True, slots=True)
class AgentTaskEvent:
    id: int
    task_id: str
    event_type: AgentEventType
    data: dict[str, object]
    created_at: str


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
