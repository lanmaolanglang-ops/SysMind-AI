from __future__ import annotations

from sysmind.domain.diagnosis import DiagnosisCategory, DiagnosisReport, Finding
from sysmind.reports.redaction import redact_text

_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}


def compose_report(
    category: DiagnosisCategory,
    findings: tuple[Finding, ...],
    limitations: tuple[str, ...],
    model_explanation: str,
) -> DiagnosisReport:
    ordered = tuple(sorted(findings, key=lambda item: _SEVERITY_RANK[item.severity], reverse=True))
    confidence = (
        round(sum(item.confidence for item in ordered) / len(ordered), 2) if ordered else 0.0
    )
    summary = ordered[0].title if ordered else "信息不足，未形成诊断结论"
    return DiagnosisReport(
        "1.0",
        summary,
        category,
        ordered,
        confidence,
        limitations,
        redact_text(model_explanation),
    )


def render_markdown(report: DiagnosisReport) -> str:
    lines = [
        "# SysMind AI 脱敏诊断报告",
        "",
        f"- 类型：{report.category}",
        f"- 摘要：{report.summary}",
        f"- 综合置信度：{report.confidence:.0%}",
        "",
        "## 结论与证据",
    ]
    for finding in report.findings:
        refs = ", ".join(f"{item.tool_call_id}:{item.field_path}" for item in finding.evidence)
        lines.extend(
            [
                "",
                f"### [{finding.severity.upper()}] {finding.title}",
                "",
                finding.explanation,
                "",
                f"证据：`{refs}`",
                "",
                f"建议：{finding.recommendation}",
                "",
                f"置信度：{finding.confidence:.0%}",
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
