from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from sysmind.domain.diagnosis import DiagnosisRecord, DiagnosisToolCall


class StartDiagnosisRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("question is too short")
        return normalized


class EvidenceDto(BaseModel):
    tool_call_id: str
    field_path: str


class FindingDto(BaseModel):
    id: str
    code: str
    severity: str
    title: str
    explanation: str
    recommendation: str
    confidence: float
    evidence: list[EvidenceDto]


class ReportDto(BaseModel):
    schema_version: str
    summary: str
    category: str
    findings: list[FindingDto]
    confidence: float
    limitations: list[str]
    model_explanation: str


class ToolCallDto(BaseModel):
    id: str
    tool_name: str
    tool_version: str
    status: str
    summary: dict[str, object] | None
    error_code: str | None


class DiagnosisResponse(BaseModel):
    id: str
    status: str
    user_question: str
    category: str
    provider: str
    plan: list[dict[str, object]]
    progress: int
    current_step: str | None
    report: ReportDto | None
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    completed_at: datetime | None
    schema_version: str
    tool_calls: list[ToolCallDto] = Field(default_factory=list)

    @classmethod
    def from_record(
        cls, record: DiagnosisRecord, calls: tuple[DiagnosisToolCall, ...] = ()
    ) -> DiagnosisResponse:
        call_data = [
            {
                "id": call.id,
                "tool_name": call.tool_name,
                "tool_version": call.tool_version,
                "status": call.status,
                "summary": call.summary,
                "error_code": call.error_code,
            }
            for call in calls
        ]
        data = asdict(record)
        data.pop("report_markdown")
        return cls.model_validate({**data, "plan": list(record.plan), "tool_calls": call_data})


class DiagnosisListResponse(BaseModel):
    items: list[DiagnosisResponse]


class DiagnosisFeedbackRequest(BaseModel):
    helpful: bool
    comment: str | None = Field(default=None, max_length=500)


class FeedbackAccepted(BaseModel):
    accepted: bool = True
