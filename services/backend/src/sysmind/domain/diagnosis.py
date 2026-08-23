from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

DiagnosisCategory: TypeAlias = Literal["performance", "network", "crash"]
DiagnosisStatus: TypeAlias = Literal[
    "queued",
    "running",
    "waiting_user_input",
    "completed",
    "partial",
    "cancelled",
    "failed",
    "interrupted",
]
Severity: TypeAlias = Literal["info", "low", "medium", "high"]
HypothesisStatus: TypeAlias = Literal["active", "confirmed", "rejected", "insufficient"]
StopReason: TypeAlias = Literal[
    "evidence_sufficient",
    "user_cancelled",
    "insufficient_information",
    "budget_exceeded",
    "risk_limit_reached",
]


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


_NON_DIAGNOSTIC_FINDING_CODES = {
    "gateway_icmp_no_response",
    "gpu_metadata_only",
    "insufficient_signal",
    "proxy_enabled",
    "stopped_automatic_services",
}


def is_diagnostic_finding(finding: Finding) -> bool:
    return finding.code not in _NON_DIAGNOSTIC_FINDING_CODES and not finding.code.startswith(
        "network_capability_"
    )


def diagnostic_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    return tuple(finding for finding in findings if is_diagnostic_finding(finding))


@dataclass(frozen=True, slots=True)
class DiagnosisHypothesis:
    id: str
    key: str
    hypothesis: str
    rationale: str
    supporting_evidence: tuple[EvidenceReference, ...]
    contradicting_evidence: tuple[EvidenceReference, ...]
    confidence: float
    status: HypothesisStatus


@dataclass(frozen=True, slots=True)
class DiagnosisReport:
    schema_version: str
    summary: str
    category: DiagnosisCategory
    findings: tuple[Finding, ...]
    confidence: float
    limitations: tuple[str, ...]
    model_explanation: str
    hypotheses: tuple[DiagnosisHypothesis, ...] = ()


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
    plan_confidence: float | None = None
    planner_status: str | None = None
    clarification_question: str | None = None
    agent_round_count: int = 0
    max_agent_rounds: int = 4
    max_tool_calls: int = 8
    stop_reason: StopReason | None = None


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
    started_at: str | None = None
    finished_at: str | None = None
