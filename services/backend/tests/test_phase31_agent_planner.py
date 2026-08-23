from __future__ import annotations

import json
from dataclasses import replace

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from sqlalchemy import text

from sysmind.agent.context import AgentContextBuilder
from sysmind.agent.contracts import ProviderAction, ProviderResponse
from sysmind.agent.planning import (
    DiagnosisPlannerError,
    FakeDiagnosisPlanner,
    PlanPayload,
    PlanStepPayload,
    ProviderDiagnosisPlanner,
    validate_plan,
)
from sysmind.agent.providers import FakeProvider
from sysmind.core.config import Settings
from sysmind.domain.diagnosis import (
    DiagnosisToolCall,
    EvidenceReference,
    Finding,
)
from sysmind.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    run_migrations,
)
from sysmind.infrastructure.database.repositories import SqlAlchemyDiagnosisRepository
from sysmind.reports.evidence import EvidenceComposer
from sysmind.tools.registry import ToolDefinition, ToolRegistry
from sysmind.tools.runtime_tools import EventLogToolInput, HighUsageInput, ProcessSnapshotInput


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _registry() -> ToolRegistry:
    definitions: list[ToolDefinition] = []
    names = (
        "system.cpu",
        "system.memory",
        "system.disks",
        "system.gpu",
        "process.high_usage",
        "process.snapshot",
        "startup.analyze",
        "network.proxy.get_config",
        "network.diagnose",
        "log.crash.analyze",
    )
    for name in names:
        if name == "log.crash.analyze":
            input_model = EventLogToolInput
        elif name == "process.high_usage":
            input_model = HighUsageInput
        elif name == "process.snapshot":
            input_model = ProcessSnapshotInput
        else:
            input_model = EmptyInput
        risk = "network" if name == "network.diagnose" else "read_only"
        definitions.append(
            ToolDefinition(
                name=name,
                version="1.0",
                description=f"Bounded test collector for {name}.",
                input_model=input_model,
                output_adapter=TypeAdapter(dict[str, object]),
                risk_level=risk,
                required_privilege="user",
                sensitivity=(),
                timeout_seconds=1,
                concurrency_key=name,
                confirmation_policy="none",
                handler=lambda _input, _cancel: {},
                summarizer=lambda value: value,  # type: ignore[arg-type]
            )
        )
    definitions.append(
        replace(
            definitions[0],
            name="process.terminate",
            risk_level="state_change",
            confirmation_policy="each_time",
        )
    )
    return ToolRegistry(tuple(definitions))


@pytest.mark.anyio
async def test_fake_planner_builds_structured_explainable_performance_plan() -> None:
    registry = _registry()
    plan = await FakeDiagnosisPlanner(registry).create_plan("电脑最近很卡")

    assert plan.problem_category == "performance"
    assert plan.confidence == pytest.approx(0.86)
    assert plan.steps
    assert all(registry.require(step.tool) and step.reason for step in plan.steps)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("question", "category", "expected_tools"),
    [
        ("电脑开机很慢", "performance", {"system.cpu@1.0", "system.memory@1.0"}),
        ("游戏掉帧", "performance", {"system.gpu@1.0"}),
        ("软件总是闪退", "crash", {"log.crash.analyze@1.0"}),
        ("无法上网", "network", {"network.diagnose@1.0"}),
    ],
)
async def test_tool_selection_matches_problem_and_records_reasons(
    question: str, category: str, expected_tools: set[str]
) -> None:
    plan = await FakeDiagnosisPlanner(_registry()).create_plan(question)
    assert plan.problem_category == category
    assert expected_tools <= {step.tool for step in plan.steps}
    assert all(len(step.reason) >= 3 for step in plan.steps)


def test_unknown_tool_invalid_arguments_and_scope_escalation_fail_closed() -> None:
    registry = _registry()
    with pytest.raises(DiagnosisPlannerError) as unknown:
        validate_plan(
            PlanPayload(
                problem_category="performance",
                confidence=0.8,
                steps=(PlanStepPayload(tool="shell.execute@1.0", reason="run command"),),
            ),
            registry,
        )
    assert unknown.value.code == "unknown_tool"

    with pytest.raises(DiagnosisPlannerError) as invalid:
        validate_plan(
            PlanPayload(
                problem_category="crash",
                confidence=0.8,
                steps=(
                    PlanStepPayload(
                        tool="log.crash.analyze@1.0",
                        reason="check crashes",
                        arguments={"lookback_hours": 999},
                    ),
                ),
            ),
            registry,
        )
    assert invalid.value.code == "invalid_arguments"

    with pytest.raises(DiagnosisPlannerError) as escalation:
        validate_plan(
            PlanPayload(
                problem_category="performance",
                confidence=0.8,
                steps=(
                    PlanStepPayload(tool="process.terminate@1.0", reason="change process state"),
                ),
            ),
            registry,
        )
    assert escalation.value.code == "tool_scope_rejected"


def test_network_scope_and_plan_budget_are_enforced() -> None:
    registry = _registry()
    network_step = PlanStepPayload(tool="network.diagnose@1.0", reason="probe network")
    with pytest.raises(DiagnosisPlannerError) as scope:
        validate_plan(
            PlanPayload(problem_category="performance", confidence=0.7, steps=(network_step,)),
            registry,
        )
    assert scope.value.code == "tool_scope_rejected"

    with pytest.raises(DiagnosisPlannerError) as budget:
        validate_plan(
            PlanPayload(problem_category="network", confidence=0.7, steps=(network_step,)),
            registry,
            max_steps=0,
        )
    assert budget.value.code == "plan_budget_exceeded"


@pytest.mark.anyio
async def test_information_shortage_asks_user_without_selecting_tools() -> None:
    plan = await FakeDiagnosisPlanner(_registry()).create_plan("不知道哪里有问题")
    assert plan.status == "ask_user"
    assert plan.steps == ()
    assert plan.clarification_question


@pytest.mark.anyio
async def test_vague_everyday_question_asks_for_actionable_context() -> None:
    plan = await FakeDiagnosisPlanner(_registry()).create_plan("帮我看看电脑")
    assert plan.status == "ask_user"
    assert plan.steps == ()
    assert "具体症状" in (plan.clarification_question or "")
    assert "发生场景" in (plan.clarification_question or "")
    assert "大致时间" in (plan.clarification_question or "")


@pytest.mark.anyio
async def test_fake_planner_revises_after_bounded_tool_observations() -> None:
    planner = FakeDiagnosisPlanner(_registry())
    plan = await planner.create_plan("电脑开机很慢")
    calls = tuple(
        DiagnosisToolCall(
            id=f"call-{index}",
            diagnosis_id="diagnosis",
            tool_name=step.tool.rsplit("@", 1)[0],
            tool_version="1.0",
            status="completed",
            result={"value": index},
            summary={"value": index},
            error_code=None,
        )
        for index, step in enumerate(plan.steps)
    )
    revision = await planner.revise_plan("电脑开机很慢", plan, calls)
    assert revision is not None
    assert {step.tool for step in revision.steps} == {
        "process.high_usage@1.0",
        "startup.analyze@1.0",
    }


@pytest.mark.anyio
async def test_provider_planner_accepts_only_structured_registry_bound_plan() -> None:
    content = json.dumps(
        {
            "problem_category": "performance",
            "confidence": 0.81,
            "status": "ready",
            "clarification_question": None,
            "steps": [{"tool": "system.memory@1.0", "reason": "check memory", "arguments": {}}],
        }
    )
    provider = FakeProvider((ProviderResponse(ProviderAction("finalize", content=content)),))
    plan = await ProviderDiagnosisPlanner(_registry(), provider).create_plan(
        r"C:\Users\PrivateName\电脑很卡"
    )
    assert plan.steps[0].tool == "system.memory@1.0"
    sent = provider.requests[0].user_goal
    assert "PrivateName" not in sent
    assert "process.terminate" not in sent
    assert provider.requests[0].tools == ()


def test_context_builder_omits_history_by_default_and_bounds_tool_catalog() -> None:
    descriptors = tuple(item.descriptor() for item in _registry().available())
    request = AgentContextBuilder(max_tools=2).build_planning_request(
        question="电脑很卡",
        tools=descriptors,
        history_summary=({"full_history": "must-not-send"},),
    )
    payload = json.loads(request.user_goal)
    assert "necessary_history" not in payload
    assert len(payload["available_tools"]) == 2


def test_evidence_composer_links_tool_fields_and_rejects_unsupported_claims() -> None:
    call = DiagnosisToolCall(
        id="call-1",
        diagnosis_id="diagnosis",
        tool_name="system.memory",
        tool_version="1.0",
        status="completed",
        result={"utilization_percent": 91.0},
        summary={"utilization_percent": 91.0},
        error_code=None,
        started_at="2026-08-23T00:00:00+00:00",
        finished_at="2026-08-23T00:00:01+00:00",
    )
    finding = Finding(
        id="finding-1",
        code="memory_pressure",
        severity="high",
        title="Memory pressure",
        explanation="Observed memory pressure.",
        recommendation="Close unneeded apps.",
        confidence=0.9,
        evidence=(EvidenceReference("call-1", "$.utilization_percent"),),
    )
    evidence = EvidenceComposer().compose(finding, (call,))[0]
    assert evidence.tool_call_id == "call-1"
    assert evidence.tool_name == "system.memory"
    assert evidence.key_fields == {"$.utilization_percent": 91.0}
    assert evidence.raw_result_summary == {"utilization_percent": 91.0}
    assert evidence.observed_at == "2026-08-23T00:00:01+00:00"

    unsupported = replace(finding, evidence=(EvidenceReference("missing-call", "$.invented"),))
    with pytest.raises(ValueError, match="missing or failed"):
        EvidenceComposer().compose(unsupported, (call,))


def test_plan_payload_schema_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PlanPayload.model_validate(
            {
                "problem_category": "performance",
                "confidence": 0.8,
                "status": "ready",
                "steps": [],
                "command": "whoami",
            }
        )


def test_plan_steps_and_decisions_are_persisted_for_audit(settings: Settings) -> None:
    run_migrations(settings.database_url)
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    repository.create(
        diagnosis_id="phase31-audit",
        question="电脑很卡",
        category="performance",
        provider="fake-planner",
        plan=(),
        created_at="2026-08-23T00:00:00+00:00",
    )
    plan = validate_plan(
        PlanPayload(
            problem_category="performance",
            confidence=0.85,
            steps=(PlanStepPayload(tool="system.memory@1.0", reason="检查内存压力"),),
        ),
        _registry(),
    )
    plan_id, step_ids = repository.save_agent_plan(
        "phase31-audit",
        provider="fake-planner",
        plan=plan.as_dict(),
        revision=1,
        created_at="2026-08-23T00:00:01+00:00",
    )
    repository.add_agent_decision(
        "phase31-audit",
        plan_id=plan_id,
        decision_type="plan_created",
        reason="检查内存压力",
        data={"tool_count": 1},
        created_at="2026-08-23T00:00:02+00:00",
    )

    engine = create_database_engine(settings.database_url)
    with engine.connect() as connection:
        counts = tuple(
            connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in ("agent_plans", "diagnosis_steps", "agent_decisions")
        )
        reason = connection.execute(
            text("SELECT reason FROM diagnosis_steps WHERE id = :id"), {"id": step_ids[0]}
        ).scalar_one()
    engine.dispose()
    assert counts == (1, 1, 1)
    assert reason == "检查内存压力"
