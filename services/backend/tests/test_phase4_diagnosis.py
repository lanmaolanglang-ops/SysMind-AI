from __future__ import annotations

import time
from threading import Event

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy import text

from sysmind.agent.contracts import ProviderAction, ProviderResponse
from sysmind.agent.planning import DiagnosisPlan, DiagnosisPlanStep
from sysmind.agent.providers import FakeProvider
from sysmind.api.app import create_app
from sysmind.core.config import Settings
from sysmind.diagnosis import DiagnosisCoordinator
from sysmind.diagnosis.planning import classify_question
from sysmind.diagnosis.rules import build_findings
from sysmind.domain.diagnosis import DiagnosisToolCall
from sysmind.infrastructure.database import create_database_engine, create_session_factory
from sysmind.infrastructure.database.repositories import SqlAlchemyDiagnosisRepository
from sysmind.prompts import LocalReportExplainer, ProviderReportExplainer
from sysmind.prompts.report_explainer import provider_request_hash
from sysmind.tools.executor import ToolExecutor
from sysmind.tools.policy import ToolPolicy
from sysmind.tools.registry import ToolDefinition, ToolRegistry
from sysmind.tools.runtime_tools import (
    EventLogToolInput,
    HighUsageInput,
    ProcessSnapshotInput,
)

_FIXTURE_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "process.snapshot": ProcessSnapshotInput,
    "process.high_usage": HighUsageInput,
    "log.crash.analyze": EventLogToolInput,
}


class AnyInput(BaseModel):
    # Match production EmptyInput: reject unknown keys (tools that take arguments
    # register the real runtime_tools input models below).
    model_config = ConfigDict(extra="forbid")


RESULTS: dict[str, object] = {
    "system.cpu": {"utilization_percent": 92.0},
    "system.gpu": [{"name": "Fixture GPU", "driver_version": "1.2.3"}],
    "system.memory": {"utilization_percent": 44.0},
    "system.disks": [{"utilization_percent": 95.0}],
    "process.high_usage": [{"name": "game.exe", "cpu_percent": 80.0}],
    "startup.analyze": {
        "item_count": 25,
        "high_impact_count": 0,
        "items": [{"location": r"C:\Users\Private Person\secret.exe"}],
    },
    "service.analyze": {"service_count": 100, "stopped_automatic_count": 1},
    "network.proxy.get_config": {"enabled": True, "server": "proxy.local"},
    "network.diagnose": {
        "adapter_count": 1,
        "has_default_route": True,
        "dns": None,
        "ping": {"loss_percent": 100.0},
        "failures": ["dns_unavailable"],
    },
    "log.crash.analyze": [
        {"application": "sample.exe", "faulting_module": "sample.dll", "count": 4}
    ],
    "process.snapshot": [],
}


def _registry(
    *,
    failing: str | None = None,
    delay: float = 0,
    results: dict[str, object] | None = None,
) -> ToolRegistry:
    fixture_results = results or RESULTS
    definitions = []
    tools = (
        "system.cpu@1.0",
        "system.gpu@1.0",
        "system.memory@1.0",
        "system.disks@1.0",
        "process.high_usage@1.0",
        "startup.analyze@1.0",
        "service.analyze@1.0",
        "network.proxy.get_config@1.0",
        "network.diagnose@1.0",
        "log.crash.analyze@1.0",
        "process.snapshot@1.0",
    )
    for tool in tools:
        name, version = tool.rsplit("@", 1)

        def handler(_input: BaseModel, _cancel: Event, tool: str = name) -> object:
            if delay:
                time.sleep(delay)
            if tool == failing:
                raise RuntimeError("private failure detail")
            return fixture_results[tool]

        definitions.append(
            ToolDefinition(
                name=name,
                version=version,
                description="Deterministic Phase 4 golden fixture.",
                input_model=_FIXTURE_INPUT_MODELS.get(name, AnyInput),
                output_adapter=TypeAdapter(dict[str, object] | list[object]),
                risk_level="network"
                if name.startswith("network.") and name != "network.proxy.get_config"
                else "read_only",
                required_privilege="user",
                sensitivity=("fixture",),
                timeout_seconds=2,
                concurrency_key=name,
                confirmation_policy="none",
                handler=handler,
                summarizer=lambda value: {"available": value is not None},
            )
        )
    return ToolRegistry(tuple(definitions))


def _coordinator(settings: Settings, registry: ToolRegistry | None = None) -> DiagnosisCoordinator:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    return DiagnosisCoordinator(repository, registry or _registry(), LocalReportExplainer)


def _wait(client: TestClient, diagnosis_id: str, headers: dict[str, str]) -> dict[str, object]:
    for _ in range(300):
        response = client.get(f"/api/v1/diagnoses/{diagnosis_id}", headers=headers)
        payload = response.json()
        if payload["status"] in {"completed", "partial", "cancelled", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("Diagnosis did not finish")


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("电脑很卡而且掉帧", "performance"),
        ("为什么无法上网，DNS 有问题吗", "network"),
        ("这个应用最近一直闪退崩溃", "crash"),
    ],
)
def test_golden_question_classification(question: str, expected: str) -> None:
    category, certain = classify_question(question)
    assert category == expected
    assert certain is True


def test_diagnosis_report_references_real_calls_and_export_is_redacted(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    coordinator = _coordinator(settings)
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑很卡"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)
        assert result["status"] == "completed"
        assert result["diagnosis_plan"]["problem_category"] == "performance"
        assert result["diagnosis_plan"]["confidence"] > 0
        assert all(step["reason"] for step in result["diagnosis_plan"]["steps"])
        call_ids = {call["id"] for call in result["tool_calls"] if call["status"] == "completed"}
        findings = result["report"]["findings"]
        assert findings
        assert all(
            evidence["tool_call_id"] in call_ids
            for finding in findings
            for evidence in finding["evidence"]
        )
        assert all(
            detail["tool_call_id"] in call_ids
            for finding in findings
            for detail in finding["evidence_details"]
        )
        assert all(
            detail["observed_at"] for finding in findings for detail in finding["evidence_details"]
        )
        hypotheses = result["report"]["hypotheses"]
        assert hypotheses
        assert all(
            evidence["tool_call_id"] in call_ids
            for hypothesis in hypotheses
            for evidence in (
                hypothesis["supporting_evidence"] + hypothesis["contradicting_evidence"]
            )
        )
        assert all(
            detail["tool_call_id"] in call_ids
            for hypothesis in hypotheses
            for detail in (
                hypothesis["supporting_evidence_details"]
                + hypothesis["contradicting_evidence_details"]
            )
        )
        exported = client.get(
            f"/api/v1/diagnoses/{created['id']}/export?format=markdown", headers=auth_headers
        )
        assert exported.status_code == 200
        assert "C:\\Users\\Private Person" not in exported.text
        assert "证据" in exported.text
        assert "来源" in exported.text
        assert "时间" in exported.text
        assert "关键指标" in exported.text
        exported_json = client.get(
            f"/api/v1/diagnoses/{created['id']}/export?format=json", headers=auth_headers
        )
        assert exported_json.status_code == 200
        assert exported_json.json()["findings"][0]["evidence_details"][0]["observed_at"]


def test_failed_tool_yields_partial_report_not_total_failure(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    coordinator = _coordinator(settings, _registry(failing="system.cpu"))
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑运行很慢"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)
        assert result["status"] == "partial"
        assert result["stop_reason"] == "evidence_sufficient"
        assert result["report"]["limitations"]
        assert result["report"]["confidence"] < 0.95
        assert "private failure detail" not in str(result)


@pytest.mark.parametrize(
    ("question", "category"),
    [
        ("电脑最近很卡", "performance"),
        ("游戏突然掉帧", "performance"),
        ("软件一直闪退", "crash"),
        ("无法联网", "network"),
        ("电脑开机很慢", "performance"),
    ],
)
def test_common_user_problem_completes_evidence_bound_product_flow(
    settings: Settings,
    auth_headers: dict[str, str],
    question: str,
    category: str,
) -> None:
    coordinator = _coordinator(settings)
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": question}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)

    assert result["category"] == category
    assert result["status"] in {"completed", "partial"}
    assert result["stop_reason"] == "evidence_sufficient"
    assert result["diagnosis_plan"]["steps"]
    assert result["tool_calls"]
    assert result["report"]["summary"] != "当前证据不足，无法确定原因。"
    assert result["report"]["findings"]
    assert result["report"]["hypotheses"]
    assert all(
        finding["recommendation"] and finding["evidence"]
        for finding in result["report"]["findings"]
    )
    assert not any(
        forbidden in step["tool"].casefold()
        for step in result["diagnosis_plan"]["steps"]
        for forbidden in ("shell", "powershell", "command", "registry")
    )


def test_startup_problem_adds_startup_evidence_without_repeating_completed_tools(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    coordinator = _coordinator(settings)
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑开机很慢"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)

    completed = [
        f"{call['tool_name']}@{call['tool_version']}"
        for call in result["tool_calls"]
        if call["status"] == "completed"
    ]
    assert "startup.analyze@1.0" in completed
    assert len(completed) == len(set(completed))


def test_startup_problem_does_not_treat_a_current_snapshot_as_boot_cause(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    results = {
        **RESULTS,
        "startup.analyze": {"item_count": 5, "high_impact_count": 0, "items": []},
    }
    coordinator = _coordinator(settings, _registry(results=results))
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑开机很慢"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)

    assert result["status"] == "partial"
    assert result["report"]["confidence"] <= 0.6
    assert any(
        "不能证明它导致开机缓慢" in limitation for limitation in result["report"]["limitations"]
    )


def test_game_problem_discloses_missing_realtime_gpu_evidence(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    coordinator = _coordinator(settings)
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "游戏突然掉帧"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)

    assert result["status"] == "partial"
    assert result["report"]["confidence"] <= 0.6
    assert any("没有 GPU 实时负载" in limitation for limitation in result["report"]["limitations"])


def test_generic_crash_problem_does_not_claim_log_relevance_without_an_app_name(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    coordinator = _coordinator(settings)
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "软件一直闪退"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)

    assert result["status"] == "partial"
    assert result["report"]["confidence"] <= 0.65
    assert any("没有具体应用名称" in limitation for limitation in result["report"]["limitations"])


def test_packet_loss_only_does_not_claim_a_network_root_cause(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    results = {
        **RESULTS,
        "network.diagnose": {
            "adapter_count": 1,
            "has_default_route": True,
            "dns": {"addresses": ["192.0.2.1"]},
            "ping": {"loss_percent": 100.0},
            "failures": [],
        },
    }
    coordinator = _coordinator(settings, _registry(results=results))
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "无法联网"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)

    assert result["status"] == "partial"
    assert result["report"]["confidence"] <= 0.65
    assert any(
        "不能单独确定无法联网的原因" in limitation for limitation in result["report"]["limitations"]
    )


def test_normal_snapshot_reports_insufficient_evidence_without_guessing(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    normal_results = {
        **RESULTS,
        "system.cpu": {"utilization_percent": 18.0},
        "system.memory": {"utilization_percent": 42.0},
        "system.disks": [{"utilization_percent": 55.0}],
        "process.high_usage": [],
        "startup.analyze": {"item_count": 5, "high_impact_count": 0, "items": []},
        "service.analyze": {"service_count": 100, "stopped_automatic_count": 0},
    }
    coordinator = _coordinator(settings, _registry(results=normal_results))
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "游戏突然掉帧"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)

    report = result["report"]
    assert result["status"] == "partial"
    assert result["stop_reason"] == "insufficient_information"
    assert report["summary"] == "当前证据不足，无法确定原因。"
    assert report["confidence"] == 0
    assert any("确定性规则阈值" in item for item in report["limitations"])
    assert all(item["status"] == "insufficient" for item in report["hypotheses"])
    assert "当前证据不足" in report["model_explanation"]


class FourRoundPlanner:
    name = "four-round-fixture"

    def __init__(self) -> None:
        self.index = 0
        self.tools = (
            "system.cpu@1.0",
            "system.memory@1.0",
            "system.disks@1.0",
            "system.gpu@1.0",
        )

    def _plan(self) -> DiagnosisPlan:
        tool = self.tools[self.index]
        return DiagnosisPlan(
            "performance",
            0.8,
            (DiagnosisPlanStep(tool, f"第 {self.index + 1} 轮只读检查", {}),),
        )

    async def create_plan(self, _question: str) -> DiagnosisPlan:
        return self._plan()

    async def revise_plan(
        self, _question: str, _plan: DiagnosisPlan, _calls: tuple[DiagnosisToolCall, ...]
    ) -> DiagnosisPlan:
        self.index += 1
        return self._plan()


def test_round_budget_stops_with_partial_report_instead_of_losing_evidence(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    planner = FourRoundPlanner()
    coordinator = DiagnosisCoordinator(
        repository,
        _registry(),
        LocalReportExplainer,
        lambda: planner,
    )
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑最近很卡"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)

    assert result["status"] == "partial"
    assert result["stop_reason"] == "budget_exceeded"
    assert len(result["tool_calls"]) == 4
    assert result["report"] is not None
    assert any("安全预算" in item for item in result["report"]["limitations"])


def test_feedback_and_history(settings: Settings, auth_headers: dict[str, str]) -> None:
    coordinator = _coordinator(settings)
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "应用闪退"}, headers=auth_headers
        ).json()
        _wait(client, created["id"], auth_headers)
        feedback = client.post(
            f"/api/v1/diagnoses/{created['id']}/feedback",
            json={"helpful": True},
            headers=auth_headers,
        )
        assert feedback.json() == {"accepted": True}
        assert client.get("/api/v1/diagnoses", headers=auth_headers).json()["items"]


@pytest.mark.anyio
async def test_report_explainer_provider_contract() -> None:
    local = LocalReportExplainer()
    assert (
        await local.explain("performance", "卡顿", ())
        == "当前证据不足，无法确定原因。建议在问题复现时重新诊断并补充发生场景。"
    )
    provider = FakeProvider(
        (ProviderResponse(ProviderAction("finalize", content="受证据约束的解释")),)
    )
    remote = ProviderReportExplainer(provider)
    assert await remote.explain("network", "C:\\Users\\Secret 无法联网", ()) == "受证据约束的解释"
    assert provider.requests[0].tools == ()
    assert "Secret" not in provider.requests[0].user_goal


def test_model_explanation_is_redacted_before_report_persistence() -> None:
    from sysmind.reports import compose_report

    report = compose_report(
        "performance",
        (),
        (),
        r"Inspect C:\Users\PrivateName\file.txt at 192.168.1.8 or a@example.com",
    )
    assert "PrivateName" not in report.model_explanation
    assert "192.168.1.8" not in report.model_explanation
    assert "a@example.com" not in report.model_explanation


def test_provider_synthesis_is_audited(settings: Settings, auth_headers: dict[str, str]) -> None:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    provider = FakeProvider(
        (ProviderResponse(ProviderAction("finalize", content="只解释已引用的证据")),)
    )
    coordinator = DiagnosisCoordinator(
        repository,
        _registry(),
        lambda: ProviderReportExplainer(provider),
    )
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑很卡"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)
        assert result["status"] == "completed"
    engine = create_database_engine(settings.database_url)
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT provider, status, request_hash, response_hash "
                "FROM diagnosis_model_calls WHERE diagnosis_id = :id"
            ),
            {"id": created["id"]},
        ).one()
    engine.dispose()
    assert row.provider == "fake"
    assert row.status == "completed"
    # Assert against the production hashing rule instead of duplicating its recipe.
    assert row.request_hash == provider_request_hash(provider.requests[0])
    assert len(row.response_hash) == 64


def test_provider_failure_degrades_to_local_report(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    provider = FakeProvider((TimeoutError("do not expose"),))
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    coordinator = DiagnosisCoordinator(
        repository,
        _registry(),
        lambda: ProviderReportExplainer(provider),
    )
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑很卡"}, headers=auth_headers
        ).json()
        result = _wait(client, created["id"], auth_headers)
    assert result["status"] == "partial"
    assert result["report"] is not None
    assert any("模型解释不可用" in item for item in result["report"]["limitations"])
    assert "do not expose" not in str(result)
    engine = create_database_engine(settings.database_url)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT request_hash FROM diagnosis_model_calls WHERE diagnosis_id = :id"),
            {"id": created["id"]},
        ).one()
    engine.dispose()
    # Assert against the production hashing rule instead of duplicating its recipe.
    assert row.request_hash == provider_request_hash(provider.requests[0])


def _network_findings(result: dict[str, object]) -> dict[str, object]:
    call = DiagnosisToolCall(
        id="network-call",
        diagnosis_id="diagnosis",
        tool_name="network.diagnose",
        tool_version="1.0",
        status="completed",
        result=result,
        summary={},
        error_code=None,
    )
    return {finding.code: finding for finding in build_findings("network", (call,))}


def test_network_probe_failure_is_visible_without_claiming_no_route() -> None:
    findings = _network_findings(
        {
            "adapter_count": 1,
            "active_adapter_count": 1,
            "has_default_route": None,
            "failures": ["default_route_unavailable", "gateway_icmp_unavailable"],
            "dns": {"addresses": ["1.1.1.1"]},
            "ping": None,
            "public_reachable": None,
        }
    )

    assert "no_default_route" not in findings
    assert "network_capability_default_route_unavailable" in findings
    assert "network_capability_gateway_icmp_unavailable" in findings


def test_empty_gateway_result_is_reported_as_no_route_not_probe_failure() -> None:
    findings = _network_findings(
        {
            "adapter_count": 1,
            "active_adapter_count": 1,
            "has_default_route": False,
            "failures": [],
            "dns": {"addresses": ["1.1.1.1"]},
            "ping": None,
        }
    )

    assert "no_default_route" in findings
    assert not any(code.startswith("network_capability_") for code in findings)


def test_adapter_fallback_references_the_field_that_exists() -> None:
    findings = _network_findings(
        {
            "adapter_count": 0,
            "has_default_route": False,
            "failures": [],
            "dns": {"addresses": []},
            "ping": None,
        }
    )

    assert findings["no_active_adapter"].evidence[0].field_path == "$.adapter_count"


def test_public_connectivity_makes_gateway_icmp_conclusion_conservative() -> None:
    findings = _network_findings(
        {
            "adapter_count": 1,
            "active_adapter_count": 1,
            "has_default_route": True,
            "gateway_reachable": False,
            "public_reachable": True,
            "failures": [],
            "dns": None,
            "ping": {"loss_percent": 0.0},
        }
    )

    assert "gateway_unreachable" not in findings
    assert "gateway_icmp_no_response" in findings
    assert "dns_failure_after_gateway_success" in findings


def test_dns_conclusion_uses_existing_public_connectivity_evidence_path() -> None:
    findings = _network_findings(
        {
            "adapter_count": 1,
            "has_default_route": True,
            "public_reachable": True,
            "failures": ["dns_unavailable"],
            "dns": None,
            "ping": None,
        }
    )

    dns_finding = findings["dns_failure_after_gateway_success"]
    assert {reference.field_path for reference in dns_finding.evidence} == {
        "$.public_reachable",
        "$.dns",
    }


def test_ambiguous_question_declares_limitation(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    coordinator = _coordinator(settings)
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses",
            json={"question": "电脑很卡，而且偶尔无法上网"},
            headers=auth_headers,
        ).json()
        result = _wait(client, created["id"], auth_headers)
        assert any("问题类型不明确" in item for item in result["report"]["limitations"])


@pytest.mark.anyio
async def test_network_tools_require_explicit_diagnosis_risk_scope() -> None:
    registry = _registry()
    denied = await ToolExecutor(ToolPolicy(registry)).execute(
        name="network.diagnose",
        version="1.0",
        arguments={},
        allowed_tools=("network.diagnose@1.0",),
        cancel_event=Event(),
    )
    assert denied.error_code == "risk_not_allowed"
    allowed = await ToolExecutor(ToolPolicy(registry, ("read_only", "network"))).execute(
        name="network.diagnose",
        version="1.0",
        arguments={},
        allowed_tools=("network.diagnose@1.0",),
        cancel_event=Event(),
    )
    assert allowed.status == "completed"


def test_diagnosis_can_be_cancelled(settings: Settings, auth_headers: dict[str, str]) -> None:
    coordinator = _coordinator(settings, _registry(delay=0.15))
    with TestClient(create_app(settings, diagnosis_coordinator=coordinator)) as client:
        created = client.post(
            "/api/v1/diagnoses", json={"question": "电脑很卡"}, headers=auth_headers
        ).json()
        client.post(f"/api/v1/diagnoses/{created['id']}/cancel", headers=auth_headers)
        result = _wait(client, created["id"], auth_headers)
        assert result["status"] == "cancelled"


def test_restart_marks_diagnosis_interrupted(settings: Settings) -> None:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(settings.database_url))
    from sysmind.infrastructure.database import run_migrations

    run_migrations(settings.database_url)
    repository.create(
        diagnosis_id="interrupted-diagnosis",
        question="电脑很卡",
        category="performance",
        provider="local-rules",
        plan=(),
        created_at="2026-08-19T10:00:00+00:00",
    )
    coordinator = DiagnosisCoordinator(repository, _registry(), LocalReportExplainer)
    assert coordinator.recover_interrupted() == 1
    assert repository.get("interrupted-diagnosis").status == "interrupted"  # type: ignore[union-attr]
