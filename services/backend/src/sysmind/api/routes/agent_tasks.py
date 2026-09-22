from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from sysmind.api.dto.agent_tasks import (
    AgentTaskListResponse,
    AgentTaskResponse,
    StartAgentTaskRequest,
    ToolCatalogResponse,
    ToolDescriptorDto,
)
from sysmind.core.constants import CORRELATION_HEADER
from sysmind.domain.agent_tasks import AgentTaskEvent
from sysmind.tasks import AgentTaskManager
from sysmind.tools.registry import ToolRegistryError

router = APIRouter(prefix="/api/v1/tasks", tags=["agent tasks"])
_TERMINAL = {
    "completed",
    "waiting_user_input",
    "cancelled",
    "failed",
    "timed_out",
    "interrupted",
}


def _manager(request: Request) -> AgentTaskManager:
    return cast(AgentTaskManager, request.app.state.agent_task_manager)


async def _response(manager: AgentTaskManager, task_id: str) -> AgentTaskResponse:
    def _build() -> AgentTaskResponse:
        record = manager.get(task_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return AgentTaskResponse.from_record(record, manager.tool_calls(task_id))

    return await run_in_threadpool(_build)


@router.get("/tools", response_model=ToolCatalogResponse)
async def available_tools(request: Request) -> ToolCatalogResponse:
    items = await run_in_threadpool(_manager(request).available_tools)
    return ToolCatalogResponse(
        items=[ToolDescriptorDto.from_descriptor(item) for item in items]
    )


@router.post("", response_model=AgentTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_agent_task(
    payload: StartAgentTaskRequest,
    request: Request,
    correlation_id: Annotated[str | None, Header(alias=CORRELATION_HEADER)] = None,
) -> AgentTaskResponse:
    manager = _manager(request)
    try:
        # Manager.start schedules asyncio tasks and must run on the event loop.
        record = manager.start(
            user_goal=payload.user_goal,
            allowed_tools=tuple(payload.allowed_tools),
            budget=payload.budget.to_domain(),
            correlation_id=correlation_id,
        )
    except ToolRegistryError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    return AgentTaskResponse.from_record(record)


@router.get("", response_model=AgentTaskListResponse)
async def recent_agent_tasks(request: Request) -> AgentTaskListResponse:
    manager = _manager(request)
    records = await run_in_threadpool(manager.recent)
    return AgentTaskListResponse(
        items=[AgentTaskResponse.from_record(record) for record in records]
    )


@router.get("/{task_id}", response_model=AgentTaskResponse)
async def get_agent_task(task_id: str, request: Request) -> AgentTaskResponse:
    return await _response(_manager(request), task_id)


@router.post("/{task_id}/cancel", response_model=AgentTaskResponse)
async def cancel_agent_task(task_id: str, request: Request) -> AgentTaskResponse:
    manager = _manager(request)

    def _cancel() -> AgentTaskResponse:
        record = manager.cancel(task_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
        return AgentTaskResponse.from_record(record, manager.tool_calls(task_id))

    return await run_in_threadpool(_cancel)


@router.get("/{task_id}/events")
async def stream_agent_task_events(
    task_id: str,
    request: Request,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    manager = _manager(request)
    if await run_in_threadpool(manager.get, task_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    try:
        cursor = int(last_event_id) if last_event_id is not None else after
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Last-Event-ID."
        ) from error
    if cursor < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event cursor.")

    def _render(event: AgentTaskEvent) -> str:
        try:
            payload = json.dumps(
                {**event.data, "created_at": event.created_at},
                ensure_ascii=False,
                default=str,
            )
        except TypeError:
            # A non-serializable payload must not drop the stream; emit an error event.
            payload = json.dumps(
                {
                    "error": {
                        "code": "event_render_failed",
                        "message": "Task event payload could not be serialized.",
                    }
                },
                ensure_ascii=False,
            )
            return f"id: {event.id}\nevent: error\ndata: {payload}\n\n"
        return f"id: {event.id}\nevent: {event.event_type}\ndata: {payload}\n\n"

    async def event_stream() -> AsyncIterator[str]:
        nonlocal cursor
        heartbeat_at = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            try:
                events = await asyncio.to_thread(manager.events_after, task_id, cursor)
                current = await asyncio.to_thread(manager.get, task_id)
            except Exception:
                # A storage error (e.g. a SQLite lock) must surface as a stream error
                # event instead of an unexplained connection drop.
                error_payload = json.dumps(
                    {
                        "error": {
                            "code": "event_stream_failed",
                            "message": "Task event stream stopped unexpectedly.",
                        }
                    },
                    ensure_ascii=False,
                )
                yield f"event: error\ndata: {error_payload}\n\n"
                return
            for event in events:
                cursor = event.id
                yield _render(event)
            if current is None:
                return
            if current.status in _TERMINAL and not events:
                # The task just reached a terminal state; give its final events one short
                # window to become visible so task.completed is not dropped.
                await asyncio.sleep(0.1)
                try:
                    trailing = await asyncio.to_thread(manager.events_after, task_id, cursor)
                except Exception:
                    trailing = []
                for event in trailing:
                    cursor = event.id
                    yield _render(event)
                return
            if time.monotonic() - heartbeat_at >= 10:
                heartbeat_at = time.monotonic()
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
