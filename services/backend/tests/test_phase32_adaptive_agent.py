from __future__ import annotations

import time
from dataclasses import replace
from threading import Event

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, TypeAdapter

from sysmind.agent.planning import DiagnosisPlan, DiagnosisPlanStep
from sysmind.api.app import create_app
from sysmind.core.config import Settings
from sysmind.diagnosis import DiagnosisCoordinator
from sysmind.diagnosis.hypotheses import HypothesisEngine
from sysmind.domain.diagnosis import EvidenceReference
from sysmind.infrastructure.database import create_session_factory, run_migrations
from sysmind.infrastructure.database.repositories import SqlAlchemyDiagnosisRepository
from sysmind.prompts import LocalReportExplainer
from sysmind.tools.registry import ToolDefinition, ToolRegistry


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _registry(*, delay: float = 0) -> ToolRegistry:
    def cpu_handler(_input: BaseModel, _cancel: Event) -> object:
        if delay:
            time.sleep(delay)
        return {"utilization_percent": 92.0}

    cpu = ToolDefinition(
        name="system.cpu",
        version="1.0",
        description="Bounded CPU fixture.",
        input_model=EmptyInput,
        output_adapter=TypeAdapter(dict[str, object]),
        risk_level="read_only",
        required_privilege="user",
        sensitivity=(),
        timeout_seconds=1,
        concurrency_key="cpu",
        confirmation_policy="none",
        handler=cpu_handler,
        summarizer=lambda value: value,  # type: ignore[arg-type]
    )
    unsafe = replace(
        cpu,
        name="process.terminate",
        description="State-changing fixture that must never execute.",
        risk_level="state_change",
        confirmation_policy="each_time",
    )
    return ToolRegistry((cpu, unsafe))


class AskThenPlanPlanner:
    name = "phase32-scripted"

    def __init__(self, *, ask_after_first_call: bool = False) -> None:
        self.create_count = 0
        self.ask_after_first_call = ask_after_first_call
        self.asked_after_call = False

    async def create_plan(self, _question: str) -> DiagnosisPlan:
        self.create_count += 1
        if self.create_count == 1 and not self.ask_after_first_call:
            return DiagnosisPlan("performance", 0.2, (), "ask_user", "卡顿主要发生在什么时间？")
        return DiagnosisPlan(
            "performance",
            0.9,
            (DiagnosisPlanStep("system.cpu@1.0", "检查 CPU 压力", {}),),
        )

    async def revise_plan(self, _question: str, _plan: DiagnosisPlan, _calls: object):
        if self.ask_after_first_call and not self.asked_after_call:
            self.asked_after_call = True
            return DiagnosisPlan("performance", 0.5, (), "ask_user", "卡顿是否只发生在开机后？")
        if self.ask_after_first_call:
            return DiagnosisPlan(
                "performance",
                0.9,
                (DiagnosisPlanStep("system.cpu@1.0", "再次检查 CPU 压力", {}),),
            )
        return None


class UnsafePlanner:
    name = "unsafe-scripted"

    async def create_plan(self, _question: str) -> DiagnosisPlan:
        return DiagnosisPlan(
            "performance",
            0.9,
            (DiagnosisPlanStep("process.terminate@1.0", "终止进程", {}),),
        )

    async def revise_plan(self, _question: str, _plan: DiagnosisPlan, _calls: object):
        return None


def _wait(
    client: TestClient,
    diagnosis_id: str,
    headers: dict[str, str],
    statuses: set[str],
) -> dict[str, object]:
    for _ in range(300):
        payload = client.get(f"/api/v1/diagnoses/{diagnosis_id}", headers=headers).json()
        if payload["status"] in statuses:
            return payload
        time.sleep(0.01)
    raise AssertionError("Diagnosis did not reach the expected state")


def test_user_answer_resumes_same_task_and_records_input(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    planner = AskThenPlanPlanner()
    coordinator = DiagnosisCoordinator(
        repository, _registry(), LocalReportExplainer, lambda: planner
    )
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "不知道哪里有问题"}, headers=auth_headers
        ).json()
        waiting = _wait(client, created["id"], auth_headers, {"waiting_user_input"})
        resumed = client.post(
            f"/api/v1/diagnoses/{created['id']}/inputs",
            json={"answer": "开机后十分钟内特别卡"},
            headers=auth_headers,
        )
        assert resumed.status_code == 202
        assert resumed.json()["id"] == created["id"]
        result = _wait(client, created["id"], auth_headers, {"completed", "partial"})

    assert waiting["stop_reason"] == "insufficient_information"
    assert result["user_inputs"] == ["开机后十分钟内特别卡"]
    assert result["agent_round_count"] == 2
    assert len(result["tool_calls"]) == 1
    assert result["stop_reason"] == "evidence_sufficient"


def test_waiting_state_survives_restart_and_can_resume(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    run_migrations(settings.database_url)
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    repository.create(
        diagnosis_id="phase32-waiting",
        question="电脑有点问题",
        category="performance",
        provider="phase32-scripted",
        plan=(),
        created_at="2026-08-23T00:00:00+00:00",
    )
    repository.wait_for_input("phase32-waiting", question="请补充症状")
    planner = AskThenPlanPlanner()
    planner.create_count = 1
    coordinator = DiagnosisCoordinator(
        repository, _registry(), LocalReportExplainer, lambda: planner
    )
    assert coordinator.recover_interrupted() == 0
    assert repository.get("phase32-waiting").status == "waiting_user_input"  # type: ignore[union-attr]

    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        response = client.post(
            "/api/v1/diagnoses/phase32-waiting/inputs",
            json={"answer": "持续卡顿"},
            headers=auth_headers,
        )
        assert response.status_code == 202
        result = _wait(client, "phase32-waiting", auth_headers, {"completed", "partial"})
    assert result["id"] == "phase32-waiting"


def test_completed_tool_is_not_repeated_after_user_input(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    planner = AskThenPlanPlanner(ask_after_first_call=True)
    coordinator = DiagnosisCoordinator(
        repository, _registry(), LocalReportExplainer, lambda: planner
    )
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑很卡"}, headers=auth_headers
        ).json()
        _wait(client, created["id"], auth_headers, {"waiting_user_input"})
        before = client.get(f"/api/v1/diagnoses/{created['id']}", headers=auth_headers).json()
        client.post(
            f"/api/v1/diagnoses/{created['id']}/inputs",
            json={"answer": "只在开机后发生"},
            headers=auth_headers,
        )
        result = _wait(client, created["id"], auth_headers, {"completed", "partial"})
    assert len(before["tool_calls"]) == 1
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["id"] == before["tool_calls"][0]["id"]


def test_hypothesis_status_transitions() -> None:
    engine = HypothesisEngine()
    support = (EvidenceReference("call", "$.value"),)
    contrary = (EvidenceReference("call", "$.other"),)
    assert (
        engine.transition(supporting_evidence=support, contradicting_evidence=(), confidence=0.9)
        == "confirmed"
    )
    assert (
        engine.transition(supporting_evidence=support, contradicting_evidence=(), confidence=0.6)
        == "active"
    )
    assert (
        engine.transition(supporting_evidence=(), contradicting_evidence=contrary, confidence=0.2)
        == "rejected"
    )
    assert (
        engine.transition(supporting_evidence=(), contradicting_evidence=(), confidence=0)
        == "insufficient"
    )


def test_unsafe_tool_plan_fails_closed_with_risk_stop_reason(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    coordinator = DiagnosisCoordinator(repository, _registry(), LocalReportExplainer, UnsafePlanner)
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑很卡"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers, {"failed"})
    assert result["stop_reason"] == "risk_limit_reached"
    assert result["failure_code"] == "tool_scope_rejected"
    assert result["tool_calls"] == []


def test_timeout_records_budget_exceeded(settings: Settings, auth_headers: dict[str, str]) -> None:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    planner = AskThenPlanPlanner()
    planner.create_count = 1
    coordinator = DiagnosisCoordinator(
        repository,
        _registry(delay=0.2),
        LocalReportExplainer,
        lambda: planner,
        active_timeout_seconds=0.02,
    )
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑很卡"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers, {"failed"})
    assert result["stop_reason"] == "budget_exceeded"
    assert result["failure_code"] == "timeout"


def test_waiting_task_cancellation_records_user_cancelled(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    planner = AskThenPlanPlanner()
    coordinator = DiagnosisCoordinator(
        repository, _registry(), LocalReportExplainer, lambda: planner
    )
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "不知道哪里有问题"}, headers=auth_headers
        ).json()
        _wait(client, created["id"], auth_headers, {"waiting_user_input"})
        cancelled = client.post(
            f"/api/v1/diagnoses/{created['id']}/cancel", headers=auth_headers
        ).json()
        duplicate_resume = client.post(
            f"/api/v1/diagnoses/{created['id']}/inputs",
            json={"answer": "电脑很卡"},
            headers=auth_headers,
        )
    assert cancelled["status"] == "cancelled"
    assert cancelled["stop_reason"] == "user_cancelled"
    assert duplicate_resume.status_code == 409
