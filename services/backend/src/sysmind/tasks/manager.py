from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event
from typing import cast

from sysmind.agent.brain import AgentBrain, AgentRunError
from sysmind.agent.contracts import AgentProvider, ToolDescriptor
from sysmind.application.ports.agent_tasks import AgentTaskRepository
from sysmind.domain.agent_tasks import (
    AgentBudget,
    AgentTaskEvent,
    AgentTaskRecord,
    AgentTaskStatus,
    AgentToolCallRecord,
)
from sysmind.observability.logging import log_event
from sysmind.security.redaction import redact_text
from sysmind.tools.executor import ToolExecutor
from sysmind.tools.policy import ToolPolicy
from sysmind.tools.registry import ToolRegistry, ToolRegistryError

AGENT_TASK_SCHEMA_VERSION = "1.0"
_LOGGER = logging.getLogger(__name__)

# Failure text is persisted and surfaced over SSE, so it is bounded and redacted.
_MAX_FAILURE_MESSAGE = 280


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_failure_message(error: AgentRunError) -> str:
    """Redact provider/adapter text before it is stored and shown to the UI.

    ``AgentRunError`` can wrap transport errors (URLs, response fragments) or adapter
    error strings. The adjacent generic handler deliberately uses fixed copy; this
    path keeps diagnostics but runs the shared redactor and clamps the length.
    """
    message = redact_text(str(error)).strip()
    if not message:
        return "Agent task failed without exposing sensitive details."
    return message[:_MAX_FAILURE_MESSAGE]


class AgentTaskManager:
    def __init__(
        self,
        repository: AgentTaskRepository,
        registry: ToolRegistry,
        provider_factory: Callable[[], AgentProvider],
        *,
        max_concurrent_tasks: int = 2,
    ) -> None:
        if not 1 <= max_concurrent_tasks <= 4:
            raise ValueError("Agent task concurrency must be between 1 and 4.")
        self._repository = repository
        self._registry = registry
        self._provider_factory = provider_factory
        self._task_semaphore = asyncio.Semaphore(max_concurrent_tasks)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancellations: dict[str, Event] = {}

    def start(
        self,
        *,
        user_goal: str,
        allowed_tools: tuple[str, ...],
        budget: AgentBudget,
        correlation_id: str | None = None,
    ) -> AgentTaskRecord:
        for qualified_name in allowed_tools:
            definition = self._registry.require(qualified_name)
            if definition.risk_level != "read_only":
                raise ToolRegistryError("Only read-only tools may enter a Phase 3 task.")
        provider = self._provider_factory()
        task_id = str(uuid.uuid4())
        record = self._repository.create(
            task_id=task_id,
            user_goal=user_goal,
            provider=provider.name,
            allowed_tools=allowed_tools,
            budget=budget,
            created_at=_now(),
            schema_version=AGENT_TASK_SCHEMA_VERSION,
        )
        self._repository.append_event(
            task_id,
            "task.created",
            {
                "status": "created",
                "provider": provider.name,
                "allowed_tool_count": len(allowed_tools),
            },
            _now(),
        )
        cancellation = Event()
        self._cancellations[task_id] = cancellation
        task = asyncio.create_task(
            self._run(record, provider, cancellation, correlation_id),
            name=f"agent-task-{task_id}",
        )
        self._tasks[task_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(task_id, None))
        return record

    def get(self, task_id: str) -> AgentTaskRecord | None:
        return self._repository.get(task_id)

    def recent(self, limit: int = 20) -> list[AgentTaskRecord]:
        return self._repository.recent(limit)

    def events_after(self, task_id: str, after_id: int) -> list[AgentTaskEvent]:
        return self._repository.events_after(task_id, after_id)

    def tool_calls(self, task_id: str) -> list[AgentToolCallRecord]:
        return self._repository.tool_calls(task_id)

    def available_tools(self) -> tuple[ToolDescriptor, ...]:
        return tuple(
            definition.descriptor()
            for definition in self._registry.available()
            if definition.risk_level == "read_only"
        )

    def cancel(self, task_id: str) -> AgentTaskRecord | None:
        record = self._repository.request_cancel(task_id)
        cancellation = self._cancellations.get(task_id)
        if cancellation:
            cancellation.set()
        return record

    def recover_interrupted(self) -> int:
        return self._repository.mark_interrupted(_now())

    async def shutdown(self) -> None:
        for cancellation in self._cancellations.values():
            cancellation.set()
        if self._tasks:
            _, pending = await asyncio.wait(tuple(self._tasks.values()), timeout=2.5)
            for task in pending:
                task.cancel()

    async def _run(
        self,
        record: AgentTaskRecord,
        provider: AgentProvider,
        cancellation: Event,
        correlation_id: str | None,
    ) -> None:
        log_event(
            _LOGGER,
            logging.INFO,
            "Agent task started.",
            component="agent_task",
            event_type="task_started",
            correlation_id=correlation_id,
            task_id=record.id,
            provider=provider.name,
        )
        try:
            async with self._task_semaphore:
                policy = ToolPolicy(self._registry)
                executor = ToolExecutor(
                    policy, max_parallel=min(4, record.budget.max_parallel_tools)
                )
                brain = AgentBrain(self._repository, self._registry, executor, provider)
                async with asyncio.timeout(record.budget.timeout_seconds):
                    await brain.run(record, cancellation)
        except TimeoutError:
            self._finish_failure(
                record, "timed_out", "task_timeout", "Agent task exceeded its time budget."
            )
        except AgentRunError as error:
            status = "cancelled" if error.code == "cancelled" else "failed"
            self._finish_failure(record, status, error.code, _safe_failure_message(error))
        except asyncio.CancelledError:
            self._finish_failure(record, "cancelled", "cancelled", "Agent task was cancelled.")
        except Exception as error:
            self._finish_failure(
                record,
                "failed",
                "internal_error",
                "Agent task failed without exposing sensitive details.",
            )
            log_event(
                _LOGGER,
                logging.ERROR,
                "Agent task failed unexpectedly.",
                component="agent_task",
                event_type="task_failed",
                correlation_id=correlation_id,
                task_id=record.id,
                error_type=type(error).__name__,
            )
        finally:
            self._cancellations.pop(record.id, None)

    def _finish_failure(
        self,
        original: AgentTaskRecord,
        status: str,
        code: str,
        message: str,
    ) -> None:
        current = self._repository.get(original.id) or original
        if current.status in {
            "completed",
            "cancelled",
            "failed",
            "timed_out",
            "interrupted",
            "waiting_user_input",
        }:
            return
        if status not in {"cancelled", "failed", "timed_out"}:
            raise ValueError("Invalid terminal task status.")
        typed_status = cast(AgentTaskStatus, status)
        self._repository.update(
            current.id,
            status=typed_status,
            current_round=current.current_round,
            tool_call_count=current.tool_call_count,
            progress=current.progress,
            working_summary=current.working_summary,
            finished_at=_now(),
            failure_code=code,
            failure_message=message,
            cancel_requested=current.cancel_requested,
        )
        self._repository.append_event(
            current.id,
            "task.failed",
            {"status": status, "code": code, "message": message},
            _now(),
        )
