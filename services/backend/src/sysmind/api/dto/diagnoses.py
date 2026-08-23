from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import cast

from pydantic import BaseModel, Field, field_validator

from sysmind.domain.diagnosis import DiagnosisRecord, DiagnosisToolCall
from sysmind.reports.evidence import EvidenceComposer


class StartDiagnosisRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("question is too short")
        return normalized


class ContinueDiagnosisRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=1000)

    @field_validator("answer")
    @classmethod
    def normalize_answer(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("answer is empty")
        return normalized


class EvidenceDto(BaseModel):
    tool_call_id: str
    field_path: str


class EvidenceDetailDto(BaseModel):
    tool_call_id: str
    tool_name: str
    tool_version: str
    key_fields: dict[str, object]
    raw_result_summary: dict[str, object]
    observed_at: datetime | None = None


class FindingDto(BaseModel):
    id: str
    code: str
    severity: str
    title: str
    explanation: str
    recommendation: str
    confidence: float
    evidence: list[EvidenceDto]
    evidence_details: list[EvidenceDetailDto] = Field(default_factory=list)


class HypothesisDto(BaseModel):
    id: str
    key: str
    hypothesis: str
    rationale: str
    supporting_evidence: list[EvidenceDto]
    contradicting_evidence: list[EvidenceDto]
    supporting_evidence_details: list[EvidenceDetailDto] = Field(default_factory=list)
    contradicting_evidence_details: list[EvidenceDetailDto] = Field(default_factory=list)
    confidence: float
    status: str


class ReportDto(BaseModel):
    schema_version: str
    summary: str
    category: str
    findings: list[FindingDto]
    confidence: float
    limitations: list[str]
    model_explanation: str
    hypotheses: list[HypothesisDto] = Field(default_factory=list)


class ToolCallDto(BaseModel):
    id: str
    tool_name: str
    tool_version: str
    status: str
    summary: dict[str, object] | None
    error_code: str | None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class StructuredDiagnosisPlanDto(BaseModel):
    problem_category: str
    confidence: float
    status: str
    clarification_question: str | None
    steps: list[dict[str, object]]


class DiagnosisResponse(BaseModel):
    id: str
    status: str
    user_question: str
    category: str
    provider: str
    plan: list[dict[str, object]]
    diagnosis_plan: StructuredDiagnosisPlanDto | None = None
    agent_round_count: int = 0
    max_agent_rounds: int = 4
    max_tool_calls: int = 8
    stop_reason: str | None = None
    user_inputs: list[str] = Field(default_factory=list)
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
        cls,
        record: DiagnosisRecord,
        calls: tuple[DiagnosisToolCall, ...] = (),
        user_inputs: tuple[str, ...] = (),
    ) -> DiagnosisResponse:
        call_data = [
            {
                "id": call.id,
                "tool_name": call.tool_name,
                "tool_version": call.tool_version,
                "status": call.status,
                "summary": call.summary,
                "error_code": call.error_code,
                "started_at": call.started_at,
                "finished_at": call.finished_at,
            }
            for call in calls
        ]
        data = asdict(record)
        data.pop("report_markdown")
        if record.report is not None:
            composer = EvidenceComposer()
            report_data = cast(dict[str, object], data["report"])
            finding_data = cast(list[dict[str, object]], report_data["findings"])
            for item, finding in zip(finding_data, record.report.findings, strict=True):
                item["evidence_details"] = [
                    asdict(evidence) for evidence in composer.compose(finding, calls)
                ]
            hypothesis_data = cast(list[dict[str, object]], report_data["hypotheses"])
            for item, hypothesis in zip(hypothesis_data, record.report.hypotheses, strict=True):
                item["supporting_evidence_details"] = [
                    asdict(evidence)
                    for evidence in composer.compose_references(
                        hypothesis.supporting_evidence, calls
                    )
                ]
                item["contradicting_evidence_details"] = [
                    asdict(evidence)
                    for evidence in composer.compose_references(
                        hypothesis.contradicting_evidence, calls
                    )
                ]
        diagnosis_plan = None
        if record.plan_confidence is not None and record.planner_status is not None:
            diagnosis_plan = {
                "problem_category": record.category,
                "confidence": record.plan_confidence,
                "status": record.planner_status,
                "clarification_question": record.clarification_question,
                "steps": list(record.plan),
            }
        return cls.model_validate(
            {
                **data,
                "plan": list(record.plan),
                "diagnosis_plan": diagnosis_plan,
                "tool_calls": call_data,
                "user_inputs": list(user_inputs),
            }
        )


class DiagnosisListResponse(BaseModel):
    items: list[DiagnosisResponse]


class DiagnosisFeedbackRequest(BaseModel):
    helpful: bool
    comment: str | None = Field(default=None, max_length=500)


class FeedbackAccepted(BaseModel):
    accepted: bool = True
