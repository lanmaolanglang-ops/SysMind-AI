from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from sysmind.api.dto.history import (
    BaselineMetricResponse,
    BaselineResponse,
    CleanupResponse,
    ConfirmDeletionRequest,
    DeletionImpactResponse,
    DeletionResponse,
    RetentionPolicyResponse,
    UpdateRetentionPolicyRequest,
)
from sysmind.application.services.history import (
    HistoryChangedError,
    HistoryProtectedError,
    HistoryService,
)

router = APIRouter(prefix="/api/v1/history", tags=["history"])
Kind = Literal["scan", "diagnosis", "log"]


def _service(request: Request) -> HistoryService:
    return cast(HistoryService, request.app.state.history_service)


@router.get("/baseline", response_model=BaselineResponse)
async def baseline(request: Request) -> BaselineResponse:
    values = await run_in_threadpool(_service(request).baseline)
    return BaselineResponse(
        items=[BaselineMetricResponse.from_value(item) for item in values]
    )


@router.get("/retention", response_model=RetentionPolicyResponse)
async def retention(request: Request) -> RetentionPolicyResponse:
    days = await run_in_threadpool(_service(request).retention_days)
    return RetentionPolicyResponse(retention_days=days)


@router.put("/retention", response_model=RetentionPolicyResponse)
async def update_retention(
    payload: UpdateRetentionPolicyRequest, request: Request
) -> RetentionPolicyResponse:
    days = await run_in_threadpool(
        _service(request).set_retention_days, payload.retention_days
    )
    return RetentionPolicyResponse(retention_days=days)


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup(request: Request) -> CleanupResponse:
    result = await run_in_threadpool(_service(request).cleanup)
    return CleanupResponse.from_value(result)


@router.get("/{kind}/{record_id}/deletion-impact", response_model=DeletionImpactResponse)
async def deletion_impact(kind: Kind, record_id: str, request: Request) -> DeletionImpactResponse:
    value = await run_in_threadpool(_service(request).impact, kind, record_id)
    if value is None:
        raise HTTPException(status_code=404, detail="History record not found.")
    return DeletionImpactResponse.from_value(value)


@router.post("/{kind}/{record_id}/delete", response_model=DeletionResponse)
async def delete_history(
    kind: Kind, record_id: str, payload: ConfirmDeletionRequest, request: Request
) -> DeletionResponse:
    try:
        await run_in_threadpool(
            _service(request).delete, kind, record_id, payload.revision
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail="History record not found.") from error
    except HistoryProtectedError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except HistoryChangedError as error:
        raise HTTPException(status_code=412, detail=str(error)) from error
    return DeletionResponse()
