from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

DiagnosisCategory: TypeAlias = Literal["performance", "network", "crash"]
DiagnosisStatus: TypeAlias = Literal[
    "queued", "running", "completed", "partial", "cancelled", "failed", "interrupted"
]
Severity: TypeAlias = Literal["info", "low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    tool_call_id: str
    field_path: str


@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    code: str
    severity: Severity
    title: str
    explanation: str
    recommendation: str
    confidence: float
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True, slots=True)
class DiagnosisReport:
    schema_version: str
    summary: str
    category: DiagnosisCategory
    findings: tuple[Finding, ...]
    confidence: float
    limitations: tuple[str, ...]
    model_explanation: str


@dataclass(frozen=True, slots=True)
class DiagnosisRecord:
    id: str
    status: DiagnosisStatus
    user_question: str
    category: DiagnosisCategory
    provider: str
    plan: tuple[dict[str, object], ...]
    progress: int
    current_step: str | None
    report: DiagnosisReport | None
    report_markdown: str | None
    failure_code: str | None
    failure_message: str | None
    created_at: str
    completed_at: str | None
    schema_version: str


@dataclass(frozen=True, slots=True)
class DiagnosisToolCall:
    id: str
    diagnosis_id: str
    tool_name: str
    tool_version: str
    status: str
    result: object | None
    summary: dict[str, object] | None
    error_code: str | None
