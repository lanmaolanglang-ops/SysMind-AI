from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, TypeVar, cast

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from starlette.concurrency import run_in_threadpool

from sysmind.actions import ActionCoordinator, ActionError
from sysmind.api.dto.actions import (
    ActionListResponse,
    ActionResponse,
    CandidateListResponse,
    ConsentResponse,
    CreateActionRequest,
    CreateProcessActionRequest,
    ExecuteActionRequest,
    ProcessCandidateListResponse,
    candidate_response,
    process_candidate_response,
)
from sysmind.application.ports.actions import ActionStateConflict
from sysmind.tools.contracts import ToolUnavailableError

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])

# Opaque ids are UUID-shaped in practice but may be echoed into headers or logs;
# keep a conservative, header-safe alphabet and bounded length (same as diagnosis ids).
ActionId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")]


def _coordinator(request: Request) -> ActionCoordinator:
    return cast(ActionCoordinator, request.app.state.action_coordinator)


T = TypeVar("T")

# Explicit status mapping. Anything not listed is a state conflict (409): consent tickets,
# expired actions, and target changes all mean "the request conflicts with current state".
_ERROR_STATUS: dict[str, int] = {
    "action_not_found": status.HTTP_404_NOT_FOUND,
    "process_actions_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _run(call: Callable[[], T]) -> T:
    try:
        return call()
    except ActionError as error:
        raise HTTPException(
            status_code=_ERROR_STATUS.get(error.code, status.HTTP_409_CONFLICT),
            detail={"code": error.code, "message": str(error)},
        ) from error
    except ActionStateConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_action_state",
                "message": "Action state changed concurrently.",
            },
        ) from error
    except ToolUnavailableError as error:
        # Platform adapters raise this when a Windows capability is missing; the
        # caller can retry later, so surface 503 instead of an opaque 500.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "tool_unavailable", "message": str(error)},
        ) from error


async def _run_async(call: Callable[[], T]) -> T:
    return await run_in_threadpool(_run, call)


@router.get("/candidates", response_model=CandidateListResponse)
async def candidates(
    request: Request, diagnosis_id: str = Query(min_length=36, max_length=36)
) -> CandidateListResponse:
    items = await _run_async(lambda: _coordinator(request).candidates(diagnosis_id))
    return CandidateListResponse(items=[candidate_response(item) for item in items])


@router.get("/process-candidates", response_model=ProcessCandidateListResponse)
async def process_candidates(
    request: Request, diagnosis_id: str = Query(min_length=36, max_length=36)
) -> ProcessCandidateListResponse:
    items = await _run_async(lambda: _coordinator(request).process_candidates(diagnosis_id))
    return ProcessCandidateListResponse(items=[process_candidate_response(item) for item in items])


@router.post("", response_model=ActionResponse, status_code=status.HTTP_201_CREATED)
async def create_action(payload: CreateActionRequest, request: Request) -> ActionResponse:
    record = await _run_async(
        lambda: _coordinator(request).create_disable(
            payload.diagnosis_id, payload.item_id, payload.observed_revision
        )
    )
    return ActionResponse.from_record(record)


@router.post("/process-close", response_model=ActionResponse, status_code=status.HTTP_201_CREATED)
async def create_process_close(
    payload: CreateProcessActionRequest, request: Request
) -> ActionResponse:
    record = await _run_async(
        lambda: _coordinator(request).create_process_close(
            payload.diagnosis_id, payload.item_id, payload.observed_revision
        )
    )
    return ActionResponse.from_record(record)


@router.post(
    "/{close_action_id}/termination",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_process_termination(
    close_action_id: ActionId, request: Request
) -> ActionResponse:
    return ActionResponse.from_record(
        await _run_async(lambda: _coordinator(request).create_process_terminate(close_action_id))
    )


@router.get("", response_model=ActionListResponse)
async def recent_actions(request: Request) -> ActionListResponse:
    items = await run_in_threadpool(_coordinator(request).recent)
    return ActionListResponse(
        items=[ActionResponse.from_record(item) for item in items]
    )


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(action_id: ActionId, request: Request) -> ActionResponse:
    record = await run_in_threadpool(_coordinator(request).get, action_id)
    if record is None:
        # Same shape as ActionError("action_not_found", ...) from _run.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "action_not_found", "message": "Action not found."},
        )
    return ActionResponse.from_record(record)


@router.post("/{action_id}/confirm", response_model=ConsentResponse)
async def confirm_action(action_id: ActionId, request: Request) -> ConsentResponse:
    record, ticket, expires = await _run_async(
        lambda: _coordinator(request).confirm(action_id)
    )
    return ConsentResponse(
        action=ActionResponse.from_record(record), ticket=ticket, expires_at=expires
    )


@router.post("/{action_id}/reject", response_model=ActionResponse)
async def reject_action(action_id: ActionId, request: Request) -> ActionResponse:
    return ActionResponse.from_record(
        await _run_async(lambda: _coordinator(request).reject(action_id))
    )


@router.post("/{action_id}/execute", response_model=ActionResponse)
async def execute_action(
    action_id: ActionId, payload: ExecuteActionRequest, request: Request
) -> ActionResponse:
    return ActionResponse.from_record(
        await _run_async(lambda: _coordinator(request).execute(action_id, payload.ticket))
    )


@router.post(
    "/{action_id}/recovery", response_model=ActionResponse, status_code=status.HTTP_201_CREATED
)
async def create_recovery(action_id: ActionId, request: Request) -> ActionResponse:
    return ActionResponse.from_record(
        await _run_async(lambda: _coordinator(request).create_restore(action_id))
    )
