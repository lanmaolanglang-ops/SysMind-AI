from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sysmind.application.ports.agent_tasks import AgentTaskRepository
from sysmind.domain.agent_tasks import (
    AgentBudget,
    AgentEventType,
    AgentTaskEvent,
    AgentTaskRecord,
    AgentTaskStatus,
    AgentToolCallRecord,
)
from sysmind.infrastructure.database.models import (
    AgentModelCall,
    AgentTask,
    AgentTaskEventModel,
    AgentToolCall,
)


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _task_record(model: AgentTask) -> AgentTaskRecord:
    budget_data = cast(dict[str, object], json.loads(model.budget_json))
    return AgentTaskRecord(
        id=model.id,
        status=cast(AgentTaskStatus, model.status),
        user_goal=model.user_goal,
        provider=model.provider,
        allowed_tools=tuple(cast(list[str], json.loads(model.allowed_tools_json))),
        budget=AgentBudget(
            max_rounds=cast(int, budget_data["max_rounds"]),
            max_tool_calls=cast(int, budget_data["max_tool_calls"]),
            timeout_seconds=cast(float, budget_data["timeout_seconds"]),
            max_parallel_tools=cast(int, budget_data["max_parallel_tools"]),
        ),
        current_round=model.current_round,
        tool_call_count=model.tool_call_count,
        progress=model.progress,
        working_summary=cast(dict[str, object], json.loads(model.working_summary_json)),
        final_output=model.final_output,
        failure_code=model.failure_code,
        failure_message=model.failure_message,
        cancel_requested=model.cancel_requested,
        created_at=model.created_at.isoformat(),
        started_at=model.started_at.isoformat() if model.started_at else None,
        finished_at=model.finished_at.isoformat() if model.finished_at else None,
        schema_version=model.schema_version,
    )


def _event_record(model: AgentTaskEventModel) -> AgentTaskEvent:
    return AgentTaskEvent(
        id=model.id,
        task_id=model.task_id,
        event_type=cast(AgentEventType, model.event_type),
        data=cast(dict[str, object], json.loads(model.data_json)),
        created_at=model.created_at.isoformat(),
    )


def _tool_record(model: AgentToolCall) -> AgentToolCallRecord:
    return AgentToolCallRecord(
        id=model.id,
        task_id=model.task_id,
        provider_call_id=model.provider_call_id,
        tool_name=model.tool_name,
        tool_version=model.tool_version,
        status=model.status,
        arguments_hash=model.arguments_hash,
        risk_level=model.risk_level,
        started_at=model.started_at.isoformat(),
        finished_at=model.finished_at.isoformat() if model.finished_at else None,
        duration_ms=model.duration_ms,
        result_summary=(
            cast(dict[str, object], json.loads(model.result_summary_json))
            if model.result_summary_json
            else None
        ),
        error_code=model.error_code,
        error_message=model.error_message,
    )


class SqlAlchemyAgentTaskRepository(AgentTaskRepository):
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

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
    ) -> AgentTaskRecord:
        with self._sessions.begin() as session:
            model = AgentTask(
                id=task_id,
                task_type="agent_runtime",
                status="created",
                user_goal=user_goal,
                provider=provider,
                allowed_tools_json=json.dumps(allowed_tools),
                budget_json=json.dumps(asdict(budget)),
                current_round=0,
                tool_call_count=0,
                progress=0,
                working_summary_json="{}",
                cancel_requested=False,
                created_at=datetime.fromisoformat(created_at),
                schema_version=schema_version,
            )
            session.add(model)
        return _task_record(model)

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
    ) -> AgentTaskRecord:
        with self._sessions.begin() as session:
            model = session.get(AgentTask, task_id)
            if model is None:
                raise KeyError(task_id)
            model.status = status
            model.current_round = current_round
            model.tool_call_count = tool_call_count
            model.progress = progress
            model.working_summary_json = json.dumps(working_summary, ensure_ascii=False)
            if started_at is not None:
                model.started_at = _parse_time(started_at)
            if finished_at is not None:
                model.finished_at = _parse_time(finished_at)
            if final_output is not None:
                model.final_output = final_output
            if failure_code is not None:
                model.failure_code = failure_code
            if failure_message is not None:
                model.failure_message = failure_message
            if cancel_requested is not None:
                model.cancel_requested = cancel_requested
        return _task_record(model)

    def request_cancel(self, task_id: str) -> AgentTaskRecord | None:
        with self._sessions.begin() as session:
            model = session.get(AgentTask, task_id)
            if model is None:
                return None
            model.cancel_requested = True
            if model.status in {"created", "planning", "running_tools", "analyzing"}:
                model.status = "cancelling"
        return _task_record(model)

    def get(self, task_id: str) -> AgentTaskRecord | None:
        with self._sessions() as session:
            model = session.get(AgentTask, task_id)
            return _task_record(model) if model else None

    def recent(self, limit: int = 20) -> list[AgentTaskRecord]:
        with self._sessions() as session:
            statement = select(AgentTask).order_by(AgentTask.created_at.desc()).limit(limit)
            return [_task_record(model) for model in session.scalars(statement)]

    def append_event(
        self,
        task_id: str,
        event_type: AgentEventType,
        data: dict[str, object],
        created_at: str,
    ) -> AgentTaskEvent:
        with self._sessions.begin() as session:
            model = AgentTaskEventModel(
                task_id=task_id,
                event_type=event_type,
                data_json=json.dumps(data, ensure_ascii=False),
                created_at=datetime.fromisoformat(created_at),
            )
            session.add(model)
            session.flush()
        return _event_record(model)

    def events_after(self, task_id: str, after_id: int, limit: int = 100) -> list[AgentTaskEvent]:
        with self._sessions() as session:
            statement = (
                select(AgentTaskEventModel)
                .where(
                    AgentTaskEventModel.task_id == task_id,
                    AgentTaskEventModel.id > after_id,
                )
                .order_by(AgentTaskEventModel.id.asc())
                .limit(limit)
            )
            return [_event_record(model) for model in session.scalars(statement)]

    def create_tool_call(
        self,
        *,
        call_id: str,
        task_id: str,
        provider_call_id: str,
        tool_name: str,
        tool_version: str,
        redacted_arguments: dict[str, object],
        arguments_hash: str,
        risk_level: str,
        started_at: str,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                AgentToolCall(
                    id=call_id,
                    task_id=task_id,
                    provider_call_id=provider_call_id,
                    tool_name=tool_name,
                    tool_version=tool_version,
                    arguments_json=json.dumps(redacted_arguments, ensure_ascii=False),
                    arguments_hash=arguments_hash,
                    risk_level=risk_level,
                    status="running",
                    started_at=datetime.fromisoformat(started_at),
                )
            )

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
    ) -> None:
        with self._sessions.begin() as session:
            model = session.get(AgentToolCall, call_id)
            if model is None:
                raise KeyError(call_id)
            model.status = status
            model.finished_at = datetime.fromisoformat(finished_at)
            model.duration_ms = duration_ms
            model.full_result_json = (
                json.dumps(full_result, ensure_ascii=False) if full_result is not None else None
            )
            model.result_summary_json = (
                json.dumps(result_summary, ensure_ascii=False)
                if result_summary is not None
                else None
            )
            model.error_code = error_code
            model.error_message = error_message

    def tool_calls(self, task_id: str) -> list[AgentToolCallRecord]:
        with self._sessions() as session:
            statement = (
                select(AgentToolCall)
                .where(AgentToolCall.task_id == task_id)
                .order_by(AgentToolCall.started_at.asc())
            )
            return [_tool_record(model) for model in session.scalars(statement)]

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
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                AgentModelCall(
                    task_id=task_id,
                    provider=provider,
                    status=status,
                    started_at=datetime.fromisoformat(started_at),
                    finished_at=datetime.fromisoformat(finished_at),
                    duration_ms=duration_ms,
                    request_hash=request_hash,
                    response_hash=response_hash,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_code=error_code,
                )
            )

    def mark_interrupted(self, finished_at: str) -> int:
        with self._sessions.begin() as session:
            statement = select(AgentTask).where(
                AgentTask.status.in_(
                    ("created", "planning", "running_tools", "analyzing", "cancelling")
                )
            )
            models = list(session.scalars(statement))
            for model in models:
                model.status = "interrupted"
                model.finished_at = datetime.fromisoformat(finished_at)
                model.failure_code = "backend_restarted"
                model.failure_message = "本地服务重启，任务未自动重放。"
                session.add(
                    AgentTaskEventModel(
                        task_id=model.id,
                        event_type="task.failed",
                        data_json=json.dumps(
                            {
                                "status": "interrupted",
                                "code": "backend_restarted",
                                "message": model.failure_message,
                            },
                            ensure_ascii=False,
                        ),
                        created_at=datetime.fromisoformat(finished_at),
                    )
                )
            return len(models)
