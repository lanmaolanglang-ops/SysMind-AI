from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Path, Request, status
from starlette.concurrency import run_in_threadpool

from sysmind.api.dto.log_analyses import (
    LogAnalysisListResponse,
    LogAnalysisResponse,
    StartLogAnalysisRequest,
)
from sysmind.application.services import LogAnalysisCoordinator
from sysmind.core.constants import CORRELATION_HEADER

router = APIRouter(prefix="/api/v1/log-analyses", tags=["log analyses"])

# Bounded, header-safe id alphabet (UUID-shaped in practice).
AnalysisId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")]


def _coordinator(request: Request) -> LogAnalysisCoordinator:
    return cast(LogAnalysisCoordinator, request.app.state.log_analysis_coordinator)


@router.post("", response_model=LogAnalysisResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_log_analysis(
    payload: StartLogAnalysisRequest,
    request: Request,
    correlation_id: Annotated[str | None, Header(alias=CORRELATION_HEADER)] = None,
) -> LogAnalysisResponse:
    # Coordinator.start schedules asyncio tasks and must run on the event loop.
    record = _coordinator(request).start(
        channels=tuple(payload.channels),
        lookback_hours=payload.lookback_hours,
        levels=tuple(payload.levels),
        event_ids=tuple(payload.event_ids),
        max_events=payload.max_events,
        correlation_id=correlation_id,
    )
    return LogAnalysisResponse.from_record(record)


@router.get("", response_model=LogAnalysisListResponse)
async def recent_log_analyses(request: Request) -> LogAnalysisListResponse:
    items = await run_in_threadpool(_coordinator(request).recent)
    return LogAnalysisListResponse(
        items=[LogAnalysisResponse.from_record(item) for item in items]
    )


@router.get("/{analysis_id}", response_model=LogAnalysisResponse)
async def get_log_analysis(analysis_id: AnalysisId, request: Request) -> LogAnalysisResponse:
    record = await run_in_threadpool(_coordinator(request).get, analysis_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return LogAnalysisResponse.from_record(record)


@router.post("/{analysis_id}/cancel", response_model=LogAnalysisResponse)
async def cancel_log_analysis(analysis_id: AnalysisId, request: Request) -> LogAnalysisResponse:
    record = await run_in_threadpool(_coordinator(request).cancel, analysis_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return LogAnalysisResponse.from_record(record)
