from __future__ import annotations

import uuid

from sysmind.domain.diagnosis import (
    DiagnosisCategory,
    DiagnosisHypothesis,
    DiagnosisToolCall,
    EvidenceReference,
    Finding,
    HypothesisStatus,
    diagnostic_findings,
)


class HypothesisEngine:
    @staticmethod
    def transition(
        *,
        supporting_evidence: tuple[EvidenceReference, ...],
        contradicting_evidence: tuple[EvidenceReference, ...],
        confidence: float,
    ) -> HypothesisStatus:
        if contradicting_evidence and not supporting_evidence:
            return "rejected"
        if supporting_evidence and confidence >= 0.8:
            return "confirmed"
        if supporting_evidence:
            return "active"
        return "insufficient"

    def build(
        self,
        category: DiagnosisCategory,
        findings: tuple[Finding, ...],
        calls: tuple[DiagnosisToolCall, ...],
        *,
        diagnosis_id: str = "standalone",
    ) -> tuple[DiagnosisHypothesis, ...]:
        hypotheses = [
            DiagnosisHypothesis(
                id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"sysmind:{diagnosis_id}:{finding.code}",
                    )
                ),
                key=finding.code,
                hypothesis=finding.title,
                rationale=finding.explanation,
                supporting_evidence=finding.evidence,
                contradicting_evidence=(),
                confidence=finding.confidence,
                status=self.transition(
                    supporting_evidence=finding.evidence,
                    contradicting_evidence=(),
                    confidence=finding.confidence,
                ),
            )
            for finding in diagnostic_findings(findings)
        ]
        if hypotheses:
            return tuple(hypotheses)

        labels = {
            "performance": "尚未确定性能问题原因",
            "network": "尚未确定网络问题原因",
            "crash": "尚未确定应用闪退原因",
        }
        return (
            DiagnosisHypothesis(
                id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"sysmind:{diagnosis_id}:{category}:root-cause",
                    )
                ),
                key=f"{category}_root_cause",
                hypothesis=labels[category],
                rationale="当前证据不足，无法确定原因。现有结果尚未达到本地确定性规则阈值。",
                supporting_evidence=(),
                contradicting_evidence=(),
                confidence=0.25 if calls else 0.0,
                status=self.transition(
                    supporting_evidence=(),
                    contradicting_evidence=(),
                    confidence=0.25,
                ),
            ),
        )
