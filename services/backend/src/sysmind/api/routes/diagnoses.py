from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from sysmind.api.dto.diagnoses import (
    ContinueDiagnosisRequest,
    DiagnosisFeedbackRequest,
    DiagnosisListResponse,
    DiagnosisResponse,
    FeedbackAccepted,
    StartDiagnosisRequest,
)
from sysmind.diagnosis import DiagnosisCoordinator
from sysmind.reports.redaction import redact_text

router = APIRouter(prefix="/api/v1/diagnoses", tags=["diagnoses"])


def _coordinator(request: Request) -> DiagnosisCoordinator:
    return cast(DiagnosisCoordinator, request.app.state.diagnosis_coordinator)


def _response(coordinator: DiagnosisCoordinator, diagnosis_id: str) -> DiagnosisResponse:
    record = coordinator.get(diagnosis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found.")
    return DiagnosisResponse.from_record(
        record,
        coordinator.tool_calls(diagnosis_id),
        coordinator.user_inputs(diagnosis_id),
    )


@router.post("", response_model=DiagnosisResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_diagnosis(payload: StartDiagnosisRequest, request: Request) -> DiagnosisResponse:
    record = _coordinator(request).start(payload.question)
    return DiagnosisResponse.from_record(record)


@router.get("", response_model=DiagnosisListResponse)
async def recent_diagnoses(request: Request) -> DiagnosisListResponse:
    coordinator = _coordinator(request)
    return DiagnosisListResponse(
        items=[
            DiagnosisResponse.from_record(
                item, coordinator.tool_calls(item.id), coordinator.user_inputs(item.id)
            )
            for item in coordinator.recent()
        ]
    )


@router.post(
    "/{diagnosis_id}/inputs",
    response_model=DiagnosisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def continue_diagnosis(
    diagnosis_id: str, payload: ContinueDiagnosisRequest, request: Request
) -> DiagnosisResponse:
    coordinator = _coordinator(request)
    if coordinator.get(diagnosis_id) is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found.")
    if coordinator.continue_with_input(diagnosis_id, payload.answer) is None:
        raise HTTPException(status_code=409, detail="Diagnosis is not waiting for user input.")
    return _response(coordinator, diagnosis_id)


@router.get("/{diagnosis_id}", response_model=DiagnosisResponse)
async def get_diagnosis(diagnosis_id: str, request: Request) -> DiagnosisResponse:
    return _response(_coordinator(request), diagnosis_id)


@router.post("/{diagnosis_id}/cancel", response_model=DiagnosisResponse)
async def cancel_diagnosis(diagnosis_id: str, request: Request) -> DiagnosisResponse:
    coordinator = _coordinator(request)
    if coordinator.cancel(diagnosis_id) is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found.")
    return _response(coordinator, diagnosis_id)


@router.post("/{diagnosis_id}/feedback", response_model=FeedbackAccepted)
async def submit_feedback(
    diagnosis_id: str, payload: DiagnosisFeedbackRequest, request: Request
) -> FeedbackAccepted:
    coordinator = _coordinator(request)
    if coordinator.get(diagnosis_id) is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found.")
    coordinator.feedback(diagnosis_id, payload.helpful, payload.comment)
    return FeedbackAccepted()


@router.get("/{diagnosis_id}/export")
async def export_diagnosis(
    diagnosis_id: str,
    request: Request,
    format: str = Query(pattern="^(json|markdown)$"),
) -> Response:
    coordinator = _coordinator(request)
    record = coordinator.get(diagnosis_id)
    if record is None or record.report is None:
        raise HTTPException(status_code=404, detail="Completed report not found.")
    if format == "markdown":
        content, media_type, suffix = record.report_markdown or "", "text/markdown", "md"
    else:
        response = DiagnosisResponse.from_record(record, coordinator.tool_calls(diagnosis_id))
        content = json.dumps(
            response.report.model_dump(mode="json") if response.report else {},
            ensure_ascii=False,
            indent=2,
        )
        media_type, suffix = "application/json", "json"
    return Response(
        content=redact_text(content),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="sysmind-report-{diagnosis_id}.{suffix}"'
        },
    )
