from __future__ import annotations

import logging
from typing import Annotated, Literal, cast

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict
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
from sysmind.observability.logging import log_event

_LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/history", tags=["history"])
Kind = Literal["scan", "diagnosis", "log"]

# Bounded, header-safe id alphabet (UUID-shaped in practice).
RecordId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")]


class CleanupConfirmRequest(BaseModel):
    """Parameter-bound confirmation: cleanup only runs with an explicit literal."""

    model_config = ConfigDict(extra="forbid")
    confirm: Literal["cleanup"]


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
async def cleanup(payload: CleanupConfirmRequest, request: Request) -> CleanupResponse:
    result = await run_in_threadpool(_service(request).cleanup)
    log_event(
        _LOGGER,
        logging.INFO,
        "History cleanup completed after explicit confirmation.",
        component="history",
        event_type="history_cleanup",
        trigger="manual",
        deleted_scans=result.deleted_scans,
        deleted_diagnoses=result.deleted_diagnoses,
        deleted_log_analyses=result.deleted_log_analyses,
        protected_records=result.protected_records,
    )
    return CleanupResponse.from_value(result)


@router.get("/{kind}/{record_id}/deletion-impact", response_model=DeletionImpactResponse)
async def deletion_impact(
    kind: Kind, record_id: RecordId, request: Request
) -> DeletionImpactResponse:
    value = await run_in_threadpool(_service(request).impact, kind, record_id)
    if value is None:
        raise HTTPException(status_code=404, detail="History record not found.")
    return DeletionImpactResponse.from_value(value)


@router.post("/{kind}/{record_id}/delete", response_model=DeletionResponse)
async def delete_history(
    kind: Kind, record_id: RecordId, payload: ConfirmDeletionRequest, request: Request
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
