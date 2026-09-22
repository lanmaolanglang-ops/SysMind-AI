from __future__ import annotations

import pytest

from sysmind.domain.actions import ACTION_TOOL_VERSIONS, MutationResult, action_tool_version
from sysmind.domain.agent_tasks import AgentBudget, AgentTaskEvent, AgentTaskRecord
from sysmind.domain.diagnosis import (
    DiagnosisHypothesis,
    DiagnosisRecord,
    DiagnosisReport,
    Finding,
)
from sysmind.domain.diagnostics import GpuInfo, ScanRecord
from sysmind.domain.platform_inspection import ServiceAssessment, ServiceInfo, StartupAssessment


def _startup(**overrides: object) -> StartupAssessment:
    payload: dict[str, object] = {
        "items": (),
        "item_count": 0,
        "high_impact_count": 0,
        "observations": (),
        "unknown_signature_count": 0,
    }
    payload.update(overrides)
    return StartupAssessment(**payload)  # type: ignore[arg-type]


def test_startup_assessment_counts_match_the_items() -> None:
    assessment = _startup(items=(), item_count=0)
    assert assessment.item_count == len(assessment.items)


def test_startup_assessment_rejects_item_count_drift() -> None:
    with pytest.raises(ValueError, match="item_count"):
        _startup(item_count=3)


def test_startup_assessment_rejects_out_of_range_subset_counts() -> None:
    with pytest.raises(ValueError, match="high_impact_count"):
        _startup(items=(), item_count=0, high_impact_count=1)
    with pytest.raises(ValueError, match="unknown_signature_count"):
        _startup(item_count=0, unknown_signature_count=-1)


def _service(**overrides: object) -> ServiceAssessment:
    payload: dict[str, object] = {
        "services": (),
        "service_count": 0,
        "stopped_automatic_count": 0,
        "observations": (),
    }
    payload.update(overrides)
    return ServiceAssessment(**payload)  # type: ignore[arg-type]


def test_service_assessment_rejects_count_drift() -> None:
    service = ServiceInfo("svc", "Service", "running", "automatic", None, None)
    with pytest.raises(ValueError, match="service_count"):
        _service(services=(service,), service_count=0)
    with pytest.raises(ValueError, match="stopped_automatic_count"):
        _service(services=(service,), service_count=1, stopped_automatic_count=2)


def test_scan_record_rejects_progress_outside_percent_range() -> None:
    with pytest.raises(ValueError, match="progress"):
        ScanRecord(
            id="s",
            status="running",
            progress=101,
            current_step=None,
            started_at="2024-01-01T00:00:00+00:00",
            finished_at=None,
            summary=None,
            failures=(),
            schema_version="1.0",
        )


def test_finding_hypothesis_report_reject_confidence_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match="confidence"):
        Finding(
            id="f",
            code="cpu_pressure",
            severity="high",
            title="t",
            explanation="e",
            recommendation="r",
            confidence=1.2,
            evidence=(),
        )
    with pytest.raises(ValueError, match="confidence"):
        DiagnosisHypothesis(
            id="h",
            key="k",
            hypothesis="h",
            rationale="r",
            supporting_evidence=(),
            contradicting_evidence=(),
            confidence=-0.1,
            status="active",
        )
    with pytest.raises(ValueError, match="confidence"):
        DiagnosisReport(
            "1.1",
            "s",
            "performance",
            (),
            2.0,
            (),
            "m",
        )


def test_agent_budget_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError, match="max_rounds"):
        AgentBudget(max_rounds=0)
    with pytest.raises(ValueError, match="max_tool_calls"):
        AgentBudget(max_tool_calls=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        AgentBudget(timeout_seconds=0.0)
    with pytest.raises(ValueError, match="max_parallel_tools"):
        AgentBudget(max_parallel_tools=0)


def test_mutable_record_fields_are_copied() -> None:
    plan_step = {"tool": "system.cpu"}
    record = DiagnosisRecord(
        id="d",
        status="queued",
        user_question="q",
        category="performance",
        provider="local",
        plan=(plan_step,),
        progress=0,
        current_step=None,
        report=None,
        report_markdown=None,
        failure_code=None,
        failure_message=None,
        created_at="2024-01-01T00:00:00+00:00",
        completed_at=None,
        schema_version="1.0",
    )
    plan_step["tool"] = "mutated"
    assert record.plan[0]["tool"] == "system.cpu"

    summary = {"rounds": 1}
    task = AgentTaskRecord(
        id="t",
        status="created",
        user_goal="g",
        provider="local",
        allowed_tools=(),
        budget=AgentBudget(),
        current_round=0,
        tool_call_count=0,
        progress=0,
        working_summary=summary,
        final_output=None,
        failure_code=None,
        failure_message=None,
        cancel_requested=False,
        created_at="2024-01-01T00:00:00+00:00",
        started_at=None,
        finished_at=None,
        schema_version="1.0",
    )
    summary["rounds"] = 99
    assert task.working_summary == {"rounds": 1}

    data = {"n": 1}
    event = AgentTaskEvent(
        id=1,
        task_id="t",
        event_type="task.created",
        data=data,
        created_at="2024-01-01T00:00:00+00:00",
    )
    data["n"] = 2
    assert event.data == {"n": 1}


def test_action_tool_versions_are_immutable_and_reject_unregistered_names() -> None:
    with pytest.raises(TypeError):
        ACTION_TOOL_VERSIONS["new.tool"] = "9.9"  # type: ignore[index]
    assert action_tool_version("startup.disable_current_user") == "1.0"
    with pytest.raises(KeyError, match="Unregistered"):
        action_tool_version("not.registered")


def test_gpu_telemetry_scope_is_typed() -> None:
    gpu = GpuInfo("Fixture GPU", 1, "1", telemetry_scope="system")
    assert gpu.telemetry_scope == "system"


def test_mutation_result_rejects_unknown_outcome() -> None:
    result = MutationResult(None, None, "closed")
    assert result.outcome == "closed"
