from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

from fastapi import APIRouter, HTTPException, Query, Request, status
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

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


def _coordinator(request: Request) -> ActionCoordinator:
    return cast(ActionCoordinator, request.app.state.action_coordinator)


T = TypeVar("T")


def _run(call: Callable[[], T]) -> T:
    try:
        return call()
    except ActionError as error:
        code = (
            status.HTTP_404_NOT_FOUND
            if error.code == "action_not_found"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(
            status_code=code, detail={"code": error.code, "message": str(error)}
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
async def create_process_termination(close_action_id: str, request: Request) -> ActionResponse:
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
async def get_action(action_id: str, request: Request) -> ActionResponse:
    record = await run_in_threadpool(_coordinator(request).get, action_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Action not found.")
    return ActionResponse.from_record(record)


@router.post("/{action_id}/confirm", response_model=ConsentResponse)
async def confirm_action(action_id: str, request: Request) -> ConsentResponse:
    record, ticket, expires = await _run_async(
        lambda: _coordinator(request).confirm(action_id)
    )
    return ConsentResponse(
        action=ActionResponse.from_record(record), ticket=ticket, expires_at=expires
    )


@router.post("/{action_id}/reject", response_model=ActionResponse)
async def reject_action(action_id: str, request: Request) -> ActionResponse:
    return ActionResponse.from_record(
        await _run_async(lambda: _coordinator(request).reject(action_id))
    )


@router.post("/{action_id}/execute", response_model=ActionResponse)
async def execute_action(
    action_id: str, payload: ExecuteActionRequest, request: Request
) -> ActionResponse:
    return ActionResponse.from_record(
        await _run_async(lambda: _coordinator(request).execute(action_id, payload.ticket))
    )


@router.post(
    "/{action_id}/recovery", response_model=ActionResponse, status_code=status.HTTP_201_CREATED
)
async def create_recovery(action_id: str, request: Request) -> ActionResponse:
    return ActionResponse.from_record(
        await _run_async(lambda: _coordinator(request).create_restore(action_id))
    )
