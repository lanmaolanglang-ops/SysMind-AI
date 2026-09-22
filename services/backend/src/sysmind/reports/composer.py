from __future__ import annotations

from dataclasses import replace

from sysmind.domain.diagnosis import (
    DiagnosisCategory,
    DiagnosisHypothesis,
    DiagnosisReport,
    DiagnosisToolCall,
    Finding,
    diagnostic_findings,
)
from sysmind.reports.evidence import EvidenceComposer
from sysmind.reports.redaction import redact_text

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}


def _clamp01(value: float) -> float:
    # Model- or rules-derived confidence is not range-checked at the domain boundary.
    return min(1.0, max(0.0, value))


def _escape_md_fence(text: str) -> str:
    # Light markdown hardening: neutralize code fences so free-form text cannot
    # break out of the report structure. Single backticks are left alone.
    return text.replace("```", "'''")


def _severity_rank(finding: Finding) -> int:
    # Unknown severities sort last instead of raising KeyError and aborting the report.
    return _SEVERITY_RANK.get(finding.severity, -1)


def _redact_finding(finding: Finding) -> Finding:
    return replace(
        finding,
        title=redact_text(finding.title),
        explanation=redact_text(finding.explanation),
        recommendation=redact_text(finding.recommendation),
    )


def _redact_hypothesis(hypothesis: DiagnosisHypothesis) -> DiagnosisHypothesis:
    return replace(
        hypothesis,
        hypothesis=redact_text(hypothesis.hypothesis),
        rationale=redact_text(hypothesis.rationale),
    )


def compose_report(
    category: DiagnosisCategory,
    findings: tuple[Finding, ...],
    limitations: tuple[str, ...],
    model_explanation: str,
    *,
    hypotheses: tuple[DiagnosisHypothesis, ...] = (),
    evidence_coverage: float = 1.0,
    confidence_cap: float = 1.0,
) -> DiagnosisReport:
    ordered = tuple(
        _redact_finding(item) for item in sorted(findings, key=_severity_rank, reverse=True)
    )
    safe_limitations = tuple(redact_text(item) for item in limitations)
    safe_hypotheses = tuple(_redact_hypothesis(item) for item in hypotheses)
    conclusions = diagnostic_findings(ordered)
    if conclusions:
        primary = conclusions[0]
        coverage = min(1.0, max(0.0, evidence_coverage))
        confidence = round(
            _clamp01(min(primary.confidence * (0.6 + 0.4 * coverage), confidence_cap)), 2
        )
        summary = primary.title
    else:
        confidence = 0.0
        summary = "当前证据不足，无法确定原因。"
    return DiagnosisReport(
        "1.1",
        summary,
        category,
        ordered,
        confidence,
        safe_limitations,
        redact_text(model_explanation),
        safe_hypotheses,
    )


def render_markdown(report: DiagnosisReport, calls: tuple[DiagnosisToolCall, ...] = ()) -> str:
    lines = [
        "# SysMind AI 脱敏诊断报告",
        "",
        f"- 类型：{report.category}",
        f"- 摘要：{redact_text(_escape_md_fence(report.summary))}",
        f"- 综合置信度：{_clamp01(report.confidence):.0%}",
        "",
        "## 结论与证据",
    ]
    composer = EvidenceComposer()
    for finding in report.findings:
        refs = ", ".join(f"{item.tool_call_id}:{item.field_path}" for item in finding.evidence)
        details = composer.compose(finding, calls) if calls else ()
        lines.extend(
            [
                "",
                f"### [{finding.severity.upper()}] {redact_text(_escape_md_fence(finding.title))}",
                "",
                redact_text(_escape_md_fence(finding.explanation)),
                "",
                f"证据：`{refs}`",
            ]
        )
        for detail in details:
            metrics = ", ".join(
                f"{path}={redact_text(value) if isinstance(value, str) else value}"
                for path, value in detail.key_fields.items()
            )
            lines.extend(
                [
                    "",
                    (
                        f"- 来源：`{detail.tool_name}@{detail.tool_version}`；"
                        f"时间：{detail.observed_at or '未记录'}；关键指标：{metrics}"
                    ),
                ]
            )
        lines.extend(
            [
                "",
                f"建议：{redact_text(_escape_md_fence(finding.recommendation))}",
                "",
                f"置信度：{_clamp01(finding.confidence):.0%}",
            ]
        )
    lines.extend(["", "## 诊断假设"])
    for hypothesis in report.hypotheses:
        supporting = (
            ", ".join(
                f"{item.tool_call_id}:{item.field_path}" for item in hypothesis.supporting_evidence
            )
            or "无"
        )
        contradicting = (
            ", ".join(
                f"{item.tool_call_id}:{item.field_path}"
                for item in hypothesis.contradicting_evidence
            )
            or "无"
        )
        title = redact_text(_escape_md_fence(hypothesis.hypothesis))
        lines.extend(
            [
                "",
                f"### [{hypothesis.status.upper()}] {title}",
                "",
                f"为什么怀疑：{redact_text(_escape_md_fence(hypothesis.rationale))}",
                "",
                f"支持证据：`{supporting}`",
                "",
                f"反证：`{contradicting}`",
                "",
                f"置信度：{_clamp01(hypothesis.confidence):.0%}",
            ]
        )
    lines.extend(
        [
            "",
            "## 辅助解释（非事实来源）",
            "",
            redact_text(_escape_md_fence(report.model_explanation)),
            "",
            "> 确定性 findings 与其证据引用始终是本报告的事实来源。",
        ]
    )
    lines.extend(["", "## 限制", ""])
    lines.extend(f"- {redact_text(_escape_md_fence(item))}" for item in report.limitations)
    return "\n".join(lines).strip() + "\n"
