from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sysmind.domain.agent_tasks import (
    AgentBudget,
    AgentEventType,
    AgentTaskEvent,
    AgentTaskRecord,
    AgentTaskStatus,
    AgentToolCallRecord,
)


class AgentTaskRepository(Protocol):
    def create(
        self,
        *,
        task_id: str,
        user_goal: str,
        provider: str,
        allowed_tools: tuple[str, ...],
        budget: AgentBudget,
        created_at: str,
        schema_version: str,
    ) -> AgentTaskRecord: ...

    def update(
        self,
        task_id: str,
        *,
        status: AgentTaskStatus,
        current_round: int,
        tool_call_count: int,
        progress: int,
        working_summary: dict[str, object],
        started_at: str | None = None,
        finished_at: str | None = None,
        final_output: str | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
        cancel_requested: bool | None = None,
        expected_statuses: Sequence[AgentTaskStatus] | None = None,
    ) -> AgentTaskRecord:
        """Compare-and-set update an agent task.

        When ``expected_statuses`` is provided the write only succeeds if the
        stored status is one of them; otherwise ``StateConflict`` is raised.
        Without it, a non-terminal write cannot revive a terminal task, and a
        terminal write cannot overwrite a *different* terminal status.
        """
        ...

    def request_cancel(self, task_id: str) -> AgentTaskRecord | None: ...

    def get(self, task_id: str) -> AgentTaskRecord | None: ...

    def recent(self, limit: int = 20) -> list[AgentTaskRecord]: ...

    def append_event(
        self,
        task_id: str,
        event_type: AgentEventType,
        data: dict[str, object],
        created_at: str,
    ) -> AgentTaskEvent: ...

    def events_after(
        self, task_id: str, after_id: int, limit: int = 100
    ) -> list[AgentTaskEvent]: ...

    def create_tool_call(
        self,
        *,
        call_id: str,
        task_id: str,
        provider_call_id: str,
        tool_name: str,
        tool_version: str,
        # Already redacted for audit: raw tool arguments must never reach the repository.
        redacted_arguments: dict[str, object],
        arguments_hash: str,
        risk_level: str,
        started_at: str,
    ) -> None: ...

    def finish_tool_call(
        self,
        call_id: str,
        *,
        status: str,
        finished_at: str,
        duration_ms: int,
        full_result: object | None,
        result_summary: dict[str, object] | None,
        error_code: str | None,
        error_message: str | None,
    ) -> None: ...

    def tool_calls(self, task_id: str) -> list[AgentToolCallRecord]: ...

    def add_model_call(
        self,
        *,
        task_id: str,
        provider: str,
        status: str,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        request_hash: str,
        response_hash: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        error_code: str | None,
    ) -> None: ...

    def mark_interrupted(self, finished_at: str) -> int: ...
