from __future__ import annotations

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


def _severity_rank(finding: Finding) -> int:
    # Unknown severities sort last instead of raising KeyError and aborting the report.
    return _SEVERITY_RANK.get(finding.severity, -1)


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
    ordered = tuple(sorted(findings, key=_severity_rank, reverse=True))
    conclusions = diagnostic_findings(ordered)
    if conclusions:
        primary = conclusions[0]
        coverage = min(1.0, max(0.0, evidence_coverage))
        confidence = round(min(primary.confidence * (0.6 + 0.4 * coverage), confidence_cap), 2)
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
        limitations,
        redact_text(model_explanation),
        hypotheses,
    )


def render_markdown(report: DiagnosisReport, calls: tuple[DiagnosisToolCall, ...] = ()) -> str:
    lines = [
        "# SysMind AI 脱敏诊断报告",
        "",
        f"- 类型：{report.category}",
        f"- 摘要：{report.summary}",
        f"- 综合置信度：{report.confidence:.0%}",
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
                f"### [{finding.severity.upper()}] {finding.title}",
                "",
                finding.explanation,
                "",
                f"证据：`{refs}`",
            ]
        )
        for detail in details:
            metrics = ", ".join(f"{path}={value}" for path, value in detail.key_fields.items())
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
                f"建议：{finding.recommendation}",
                "",
                f"置信度：{finding.confidence:.0%}",
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
        lines.extend(
            [
                "",
                f"### [{hypothesis.status.upper()}] {hypothesis.hypothesis}",
                "",
                f"为什么怀疑：{hypothesis.rationale}",
                "",
                f"支持证据：`{supporting}`",
                "",
                f"反证：`{contradicting}`",
                "",
                f"置信度：{hypothesis.confidence:.0%}",
            ]
        )
    lines.extend(
        [
            "",
            "## 辅助解释（非事实来源）",
            "",
            report.model_explanation,
            "",
            "> 确定性 findings 与其证据引用始终是本报告的事实来源。",
        ]
    )
    lines.extend(["", "## 限制", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    return "\n".join(lines).strip() + "\n"
