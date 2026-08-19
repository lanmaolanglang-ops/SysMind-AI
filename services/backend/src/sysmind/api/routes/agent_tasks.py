from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from sysmind.api.dto.agent_tasks import (
    AgentTaskListResponse,
    AgentTaskResponse,
    StartAgentTaskRequest,
    ToolCatalogResponse,
    ToolDescriptorDto,
)
from sysmind.core.constants import CORRELATION_HEADER
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


def _response(manager: AgentTaskManager, task_id: str) -> AgentTaskResponse:
    record = manager.get(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return AgentTaskResponse.from_record(record, manager.tool_calls(task_id))


@router.get("/tools", response_model=ToolCatalogResponse)
async def available_tools(request: Request) -> ToolCatalogResponse:
    return ToolCatalogResponse(
        items=[
            ToolDescriptorDto.from_descriptor(item) for item in _manager(request).available_tools()
        ]
    )


@router.post("", response_model=AgentTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_agent_task(
    payload: StartAgentTaskRequest,
    request: Request,
    correlation_id: Annotated[str | None, Header(alias=CORRELATION_HEADER)] = None,
) -> AgentTaskResponse:
    manager = _manager(request)
    try:
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
    return AgentTaskListResponse(
        items=[AgentTaskResponse.from_record(record) for record in manager.recent()]
    )


@router.get("/{task_id}", response_model=AgentTaskResponse)
async def get_agent_task(task_id: str, request: Request) -> AgentTaskResponse:
    return _response(_manager(request), task_id)


@router.post("/{task_id}/cancel", response_model=AgentTaskResponse)
async def cancel_agent_task(task_id: str, request: Request) -> AgentTaskResponse:
    manager = _manager(request)
    record = manager.cancel(task_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return AgentTaskResponse.from_record(record, manager.tool_calls(task_id))


@router.get("/{task_id}/events")
async def stream_agent_task_events(
    task_id: str,
    request: Request,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    manager = _manager(request)
    if manager.get(task_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    try:
        cursor = int(last_event_id) if last_event_id is not None else after
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Last-Event-ID."
        ) from error
    if cursor < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event cursor.")

    async def event_stream() -> AsyncIterator[str]:
        nonlocal cursor
        heartbeat_at = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            events = await asyncio.to_thread(manager.events_after, task_id, cursor)
            for event in events:
                cursor = event.id
                payload = json.dumps(
                    {**event.data, "created_at": event.created_at}, ensure_ascii=False
                )
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {payload}\n\n"
            current = await asyncio.to_thread(manager.get, task_id)
            if current is None or (current.status in _TERMINAL and not events):
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
