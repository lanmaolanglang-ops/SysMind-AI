from __future__ import annotations

import json
from typing import Annotated, cast

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, Response, status
from starlette.concurrency import run_in_threadpool

from sysmind.api.dto.diagnoses import (
    ContinueDiagnosisRequest,
    DiagnosisFeedbackRequest,
    DiagnosisListResponse,
    DiagnosisResponse,
    FeedbackAccepted,
    StartDiagnosisRequest,
)
from sysmind.core.constants import CORRELATION_HEADER
from sysmind.diagnosis import DiagnosisCoordinator
from sysmind.reports.redaction import redact_text

router = APIRouter(prefix="/api/v1/diagnoses", tags=["diagnoses"])

# Diagnosis ids are opaque strings, but they are echoed into a Content-Disposition header,
# so the parameter is restricted to a conservative, header-safe alphabet and bounded length.
DiagnosisId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")]


def _coordinator(request: Request) -> DiagnosisCoordinator:
    return cast(DiagnosisCoordinator, request.app.state.diagnosis_coordinator)


async def _threadpool_response(
    coordinator: DiagnosisCoordinator, diagnosis_id: str
) -> DiagnosisResponse:
    def _build() -> DiagnosisResponse:
        record = coordinator.get(diagnosis_id)
        if record is None:
            raise LookupError(diagnosis_id)
        return DiagnosisResponse.from_record(
            record,
            coordinator.tool_calls(diagnosis_id),
            coordinator.user_inputs(diagnosis_id),
        )

    try:
        return await run_in_threadpool(_build)
    except LookupError:
        raise HTTPException(status_code=404, detail="Diagnosis not found.") from None


@router.post("", response_model=DiagnosisResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_diagnosis(
    payload: StartDiagnosisRequest,
    request: Request,
    correlation_id: Annotated[str | None, Header(alias=CORRELATION_HEADER)] = None,
) -> DiagnosisResponse:
    # Coordinator.start schedules asyncio tasks and must run on the event loop.
    record = _coordinator(request).start(payload.question, correlation_id=correlation_id)
    return DiagnosisResponse.from_record(record)


@router.get("", response_model=DiagnosisListResponse)
async def recent_diagnoses(request: Request) -> DiagnosisListResponse:
    coordinator = _coordinator(request)

    def _build() -> DiagnosisListResponse:
        items = [
            DiagnosisResponse.from_record(
                item, coordinator.tool_calls(item.id), coordinator.user_inputs(item.id)
            )
            for item in coordinator.recent()
        ]
        return DiagnosisListResponse(items=items)

    return await run_in_threadpool(_build)


@router.post(
    "/{diagnosis_id}/inputs",
    response_model=DiagnosisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def continue_diagnosis(
    diagnosis_id: DiagnosisId, payload: ContinueDiagnosisRequest, request: Request
) -> DiagnosisResponse:
    coordinator = _coordinator(request)
    if await run_in_threadpool(coordinator.get, diagnosis_id) is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found.")
    # continue_with_input schedules asyncio tasks and must run on the event loop.
    if coordinator.continue_with_input(diagnosis_id, payload.answer) is None:
        raise HTTPException(status_code=409, detail="Diagnosis is not waiting for user input.")
    return await _threadpool_response(coordinator, diagnosis_id)


@router.get("/{diagnosis_id}", response_model=DiagnosisResponse)
async def get_diagnosis(diagnosis_id: DiagnosisId, request: Request) -> DiagnosisResponse:
    return await _threadpool_response(_coordinator(request), diagnosis_id)


@router.post("/{diagnosis_id}/cancel", response_model=DiagnosisResponse)
async def cancel_diagnosis(
    diagnosis_id: DiagnosisId,
    request: Request,
    # Accepted for request/task tracing parity with start_diagnosis (CORS already allows it).
    correlation_id: Annotated[str | None, Header(alias=CORRELATION_HEADER)] = None,
) -> DiagnosisResponse:
    del correlation_id
    coordinator = _coordinator(request)
    if await run_in_threadpool(coordinator.cancel, diagnosis_id) is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found.")
    return await _threadpool_response(coordinator, diagnosis_id)


@router.post("/{diagnosis_id}/feedback", response_model=FeedbackAccepted)
async def submit_feedback(
    diagnosis_id: DiagnosisId, payload: DiagnosisFeedbackRequest, request: Request
) -> FeedbackAccepted:
    coordinator = _coordinator(request)
    if await run_in_threadpool(coordinator.get, diagnosis_id) is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found.")
    await run_in_threadpool(
        coordinator.feedback, diagnosis_id, payload.helpful, payload.comment
    )
    return FeedbackAccepted()


@router.get("/{diagnosis_id}/export")
async def export_diagnosis(
    diagnosis_id: DiagnosisId,
    request: Request,
    export_format: str = Query(alias="format", pattern="^(json|markdown)$"),
) -> Response:
    coordinator = _coordinator(request)

    def _export() -> tuple[str, str, str]:
        record = coordinator.get(diagnosis_id)
        if record is None or record.report is None:
            raise LookupError(diagnosis_id)
        if export_format == "markdown":
            content, media_type, suffix = record.report_markdown or "", "text/markdown", "md"
        else:
            response = DiagnosisResponse.from_record(record, coordinator.tool_calls(diagnosis_id))
            content = json.dumps(
                response.report.model_dump(mode="json") if response.report else {},
                ensure_ascii=False,
                indent=2,
            )
            media_type, suffix = "application/json", "json"
        return content, media_type, suffix

    try:
        content, media_type, suffix = await run_in_threadpool(_export)
    except LookupError:
        raise HTTPException(status_code=404, detail="Completed report not found.") from None
    return Response(
        content=redact_text(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="sysmind-report-{diagnosis_id}.{suffix}"'
        },
    )
