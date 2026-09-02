from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psutil
import pytest
from fastapi.testclient import TestClient

from sysmind.actions import ActionCoordinator, ActionError
from sysmind.api.dto.actions import ActionResponse
from sysmind.application.ports.actions import ActionVerificationError
from sysmind.domain.actions import (
    MutationResult,
    ProcessActionCandidate,
    StartupActionCandidate,
)
from sysmind.infrastructure.database import create_session_factory, run_migrations
from sysmind.infrastructure.database.models import ActionModel, Diagnosis, DiagnosisToolCallModel
from sysmind.infrastructure.database.repositories import (
    SqlAlchemyActionRepository,
    SqlAlchemyDiagnosisRepository,
)
from sysmind.security import ConsentService
from sysmind.tools.contracts import ToolUnavailableError
from sysmind.windows.process_actions import WindowsProcessActionAdapter
from sysmind.windows.startup_actions import TargetChangedError


class FakeStartupActions:
    def __init__(self) -> None:
        self.item = StartupActionCandidate("a" * 64, "Example", "user_run", "example.exe", "b" * 64)
        self.enabled = True
        self.recoveries: set[str] = set()
        self.fail_verification = False

    def candidates(self) -> tuple[StartupActionCandidate, ...]:
        return (self.item,) if self.enabled else ()

    def disable(self, item_id: str, observed_revision: str) -> MutationResult:
        if (
            not self.enabled
            or item_id != self.item.item_id
            or observed_revision != self.item.observed_revision
        ):
            raise TargetChangedError("changed")
        self.enabled = False
        self.recoveries.add("recovery-1")
        if self.fail_verification:
            raise ActionVerificationError(
                "Startup action could not be verified.", recovery_id="recovery-1"
            )
        return MutationResult("recovery-1", None)

    def restore(self, recovery_id: str) -> MutationResult:
        if recovery_id not in self.recoveries or self.enabled:
            raise TargetChangedError("changed")
        self.recoveries.remove(recovery_id)
        self.enabled = True
        return MutationResult(None, self.item.observed_revision)

    def recovery_exists(self, recovery_id: str) -> bool:
        return recovery_id in self.recoveries


class FakeProcessActions:
    def __init__(self, outcome: str = "closed") -> None:
        self.item = ProcessActionCandidate(
            "d" * 64,
            "Editor.exe",
            "current_user_process",
            "editor.exe",
            "e" * 64,
            4242,
            42.0,
            12.0,
        )
        self.outcome = outcome
        self.calls = 0
        self.terminate_calls = 0

    def candidates(self) -> tuple[ProcessActionCandidate, ...]:
        return (self.item,)

    def request_close(self, item_id: str, observed_revision: str) -> MutationResult:
        if item_id != self.item.item_id or observed_revision != self.item.observed_revision:
            raise TargetChangedError("changed")
        self.calls += 1
        return MutationResult(None, None, self.outcome)

    def terminate(self, item_id: str, observed_revision: str) -> MutationResult:
        if item_id != self.item.item_id or observed_revision != self.item.observed_revision:
            raise TargetChangedError("changed")
        self.terminate_calls += 1
        return MutationResult(None, None, "terminated")


def coordinator(
    tmp_path: Path,
    process_adapter: FakeProcessActions | None = None,
    *,
    diagnosis_id: str = "diagnosis-ready",
) -> tuple[ActionCoordinator, FakeStartupActions]:
    database_url = f"sqlite:///{(tmp_path / 'actions.db').as_posix()}"
    run_migrations(database_url)
    sessions = create_session_factory(database_url)
    now = datetime.now(UTC)
    with sessions.begin() as session:
        session.add(
            Diagnosis(
                id=diagnosis_id,
                status="completed",
                user_question="slow",
                category="performance",
                provider="fake",
                plan_json="[]",
                progress=100,
                created_at=now,
                completed_at=now,
                report_json=json.dumps(
                    {
                        "schema_version": "1.0",
                        "summary": "high usage",
                        "category": "performance",
                        "findings": [
                            {
                                "id": "finding-process",
                                "code": "resource_competition",
                                "severity": "medium",
                                "title": "high usage",
                                "explanation": "evidence",
                                "recommendation": "review",
                                "confidence": 0.8,
                                "evidence": [
                                    {
                                        "tool_call_id": "process-call",
                                        "field_path": "$",
                                    }
                                ],
                            }
                        ],
                        "confidence": 0.8,
                        "limitations": [],
                        "model_explanation": "local",
                    }
                ),
                schema_version="1.0",
            )
        )
        session.add(
            DiagnosisToolCallModel(
                id="startup-call",
                diagnosis_id=diagnosis_id,
                tool_name="startup.analyze",
                tool_version="1.0",
                arguments_json="{}",
                arguments_hash="c" * 64,
                status="completed",
                result_json="{}",
                started_at=now,
                finished_at=now,
                duration_ms=1,
            )
        )
        session.add(
            DiagnosisToolCallModel(
                id="process-call",
                diagnosis_id=diagnosis_id,
                tool_name="process.high_usage",
                tool_version="1.0",
                arguments_json="{}",
                arguments_hash="f" * 64,
                status="completed",
                result_json=json.dumps([{"pid": 4242, "name": "Editor.exe"}]),
                started_at=now,
                finished_at=now,
                duration_ms=1,
            )
        )
    adapter = FakeStartupActions()
    return ActionCoordinator(
        SqlAlchemyActionRepository(sessions),
        SqlAlchemyDiagnosisRepository(sessions),
        adapter,
        ConsentService("session"),
        process_adapter,
    ), adapter


def test_disable_requires_bound_single_use_consent_and_can_recover(tmp_path: Path) -> None:
    service, adapter = coordinator(tmp_path)
    candidate = service.candidates("diagnosis-ready")[0]
    action = service.create_disable(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    confirmed, ticket, _expires = service.confirm(action.id)
    assert confirmed.status == "confirmed"
    with pytest.raises(ActionError, match="invalid"):
        service.execute(action.id, ticket + "tampered")
    completed = service.execute(action.id, ticket)
    assert completed.status == "succeeded"
    assert completed.recovery_id == "recovery-1"
    assert adapter.enabled is False
    with pytest.raises(ActionError, match="awaiting execution"):
        service.execute(action.id, ticket)

    restore = service.create_restore(action.id)
    _confirmed, restore_ticket, _expires = service.confirm(restore.id)
    restored = service.execute(restore.id, restore_ticket)
    assert restored.status == "succeeded"
    assert adapter.enabled is True
    with pytest.raises(ActionError) as error:
        service.create_restore(action.id)
    assert error.value.code == "recovery_unavailable"


def test_target_revision_change_fails_closed(tmp_path: Path) -> None:
    service, adapter = coordinator(tmp_path)
    candidate = service.candidates("diagnosis-ready")[0]
    with pytest.raises(ActionError, match="changed"):
        service.create_disable("diagnosis-ready", candidate.item_id, "d" * 64)
    action = service.create_disable(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    _confirmed, ticket, _expires = service.confirm(action.id)
    adapter.item = StartupActionCandidate(
        candidate.item_id, candidate.name, candidate.source_kind, candidate.command_name, "e" * 64
    )
    result = service.execute(action.id, ticket)
    assert result.status == "target_changed"


def test_disable_verification_failure_keeps_recovery_chain(tmp_path: Path) -> None:
    service, adapter = coordinator(tmp_path)
    adapter.fail_verification = True
    candidate = service.candidates("diagnosis-ready")[0]
    action = service.create_disable(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    _confirmed, ticket, _expires = service.confirm(action.id)

    result = service.execute(action.id, ticket)

    assert result.status == "verification_failed"
    assert result.recovery_id == "recovery-1"
    assert adapter.recovery_exists("recovery-1")
    assert ActionResponse.from_record(result).recovery_available is True

    restore = service.create_restore(result.id)
    _confirmed, restore_ticket, _expires = service.confirm(restore.id)
    restored = service.execute(restore.id, restore_ticket)
    assert restored.status == "succeeded"
    assert adapter.enabled is True


def test_diagnosis_without_startup_evidence_is_rejected(tmp_path: Path) -> None:
    service, _adapter = coordinator(tmp_path)
    with pytest.raises(ActionError, match="completed diagnosis"):
        service.candidates("missing")


@pytest.mark.parametrize(
    ("outcome", "expected_status"), (("closed", "succeeded"), ("close_pending", "close_pending"))
)
def test_process_close_is_evidence_bound_and_never_auto_escalates(
    tmp_path: Path, outcome: str, expected_status: str
) -> None:
    process = FakeProcessActions(outcome)
    service, _startup = coordinator(tmp_path, process)
    candidate = service.process_candidates("diagnosis-ready")[0]
    action = service.create_process_close(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    _confirmed, ticket, _expires = service.confirm(action.id)
    result = service.execute(action.id, ticket)

    assert result.status == expected_status
    assert process.calls == 1
    assert result.recovery_id is None
    if outcome == "close_pending":
        assert result.error_code == "close_pending"


def test_process_close_plan_expires_before_execution(tmp_path: Path) -> None:
    process = FakeProcessActions()
    service, _startup = coordinator(tmp_path, process)
    candidate = service.process_candidates("diagnosis-ready")[0]
    action = service.create_process_close(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    _confirmed, ticket, _expires = service.confirm(action.id)
    sessions = create_session_factory(f"sqlite:///{(tmp_path / 'actions.db').as_posix()}")
    with sessions.begin() as session:
        model = session.get(ActionModel, action.id)
        assert model is not None
        model.created_at = datetime.now(UTC) - timedelta(seconds=31)

    result = service.execute(action.id, ticket)
    assert result.status == "target_changed"
    assert process.calls == 0


def test_forced_termination_requires_pending_close_and_two_confirmations(
    tmp_path: Path,
) -> None:
    process = FakeProcessActions("close_pending")
    service, _startup = coordinator(tmp_path, process)
    candidate = service.process_candidates("diagnosis-ready")[0]
    close = service.create_process_close(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    _confirmed, close_ticket, _expires = service.confirm(close.id)
    assert close_ticket is not None
    pending = service.execute(close.id, close_ticket)
    assert pending.status == "close_pending"

    termination = service.create_process_terminate(pending.id)
    stage_one, ticket, expires = service.confirm(termination.id)
    assert stage_one.status == "awaiting_second_confirmation"
    assert ticket is None and expires is None
    stage_two, ticket, expires = service.confirm(termination.id)
    assert stage_two.status == "confirmed"
    assert ticket is not None and expires is not None
    result = service.execute(termination.id, ticket)
    assert result.status == "succeeded"
    assert process.terminate_calls == 1
    assert result.recovery_id is None


def test_forced_termination_cannot_be_created_after_successful_close(tmp_path: Path) -> None:
    process = FakeProcessActions("closed")
    service, _startup = coordinator(tmp_path, process)
    candidate = service.process_candidates("diagnosis-ready")[0]
    close = service.create_process_close(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    _confirmed, ticket, _expires = service.confirm(close.id)
    assert ticket is not None
    completed = service.execute(close.id, ticket)
    with pytest.raises(ActionError) as error:
        service.create_process_terminate(completed.id)
    assert error.value.code == "termination_not_allowed"


def test_restart_invalidates_first_termination_confirmation(tmp_path: Path) -> None:
    process = FakeProcessActions("close_pending")
    service, _startup = coordinator(tmp_path, process)
    candidate = service.process_candidates("diagnosis-ready")[0]
    close = service.create_process_close(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    _confirmed, close_ticket, _expires = service.confirm(close.id)
    assert close_ticket is not None
    pending = service.execute(close.id, close_ticket)
    termination = service.create_process_terminate(pending.id)
    stage_one, ticket, expires = service.confirm(termination.id)
    assert stage_one.status == "awaiting_second_confirmation"
    assert ticket is None and expires is None

    assert service.recover_interrupted() == 1
    interrupted = service.get(termination.id)
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert interrupted.error_code == "backend_restarted"
    with pytest.raises(ActionError) as error:
        service.confirm(termination.id)
    assert error.value.code == "invalid_action_state"


def test_second_termination_confirmation_expires_with_plan(tmp_path: Path) -> None:
    process = FakeProcessActions("close_pending")
    service, _startup = coordinator(tmp_path, process)
    candidate = service.process_candidates("diagnosis-ready")[0]
    close = service.create_process_close(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    _confirmed, close_ticket, _expires = service.confirm(close.id)
    assert close_ticket is not None
    pending = service.execute(close.id, close_ticket)
    termination = service.create_process_terminate(pending.id)
    stage_one, _ticket, _expires = service.confirm(termination.id)
    sessions = create_session_factory(f"sqlite:///{(tmp_path / 'actions.db').as_posix()}")
    with sessions.begin() as session:
        model = session.get(ActionModel, termination.id)
        assert model is not None
        model.created_at = datetime.now(UTC) - timedelta(seconds=31)

    with pytest.raises(ActionError) as error:
        service.confirm(stage_one.id)
    assert error.value.code == "action_expired"
    expired = service.get(termination.id)
    assert expired is not None and expired.status == "expired"
    assert process.terminate_calls == 0


def test_process_post_state_access_denied_is_not_reported_as_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = FakeProcessActions().item

    def denied(_pid: int) -> psutil.Process:
        raise psutil.AccessDenied(candidate.pid)

    monkeypatch.setattr(psutil, "Process", denied)
    with pytest.raises(ToolUnavailableError, match="could not be verified"):
        WindowsProcessActionAdapter()._same_process(candidate)


def test_process_candidates_only_sample_visible_pids_and_normalize_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid
            self._cpu_calls = 0

        def as_dict(self, attrs: object) -> dict[str, object]:
            del attrs
            return {
                "pid": self.pid,
                "name": "Editor.exe",
                "create_time": 100.0,
                "exe": r"C:\Program Files\Editor\Editor.exe",
            }

        def cpu_percent(self, interval: object = None) -> float:
            del interval
            self._cpu_calls += 1
            return 0.0 if self._cpu_calls == 1 else 320.0

        def memory_percent(self) -> float:
            return 5.0

    adapter = WindowsProcessActionAdapter()
    constructed: list[int] = []

    def process(pid: int) -> FakeProcess:
        constructed.append(pid)
        return FakeProcess(pid)

    monkeypatch.setattr("sysmind.windows.process_actions.os.name", "nt")
    monkeypatch.setattr(adapter, "_visible_windows", lambda: {42: (1001,)})
    monkeypatch.setattr(adapter, "_process_sid", lambda _pid: "S-1-fixture")
    monkeypatch.setattr(adapter, "_session_id", lambda _pid: 1)
    monkeypatch.setattr(adapter, "_elevation_type", lambda _pid: 1)
    monkeypatch.setattr(adapter, "_sysmind_process_tree", lambda: set())
    monkeypatch.setattr(adapter, "_is_critical", lambda _pid: False)
    monkeypatch.setattr("sysmind.windows.process_actions.psutil.Process", process)
    monkeypatch.setattr("sysmind.windows.diagnostics.psutil.cpu_count", lambda logical=True: 8)
    monkeypatch.setattr("sysmind.windows.process_actions.time.sleep", lambda _seconds: None)

    candidates = adapter.candidates()

    assert constructed == [42]
    assert candidates[0].cpu_percent == 40.0


def test_process_action_api_preserves_pending_and_double_confirmation_contract(
    tmp_path: Path,
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    diagnosis_id = "00000000-0000-4000-8000-000000000005"
    process = FakeProcessActions("close_pending")
    service, _startup = coordinator(tmp_path, process, diagnosis_id=diagnosis_id)
    original = client.app.state.action_coordinator
    client.app.state.action_coordinator = service
    try:
        candidates = client.get(
            f"/api/v1/actions/process-candidates?diagnosis_id={diagnosis_id}",
            headers=auth_headers,
        )
        assert candidates.status_code == 200
        candidate = candidates.json()["items"][0]
        assert "pid" not in candidate

        created = client.post(
            "/api/v1/actions/process-close",
            headers=auth_headers,
            json={
                "diagnosis_id": diagnosis_id,
                "item_id": candidate["item_id"],
                "observed_revision": candidate["observed_revision"],
            },
        )
        close_id = created.json()["id"]
        consent = client.post(f"/api/v1/actions/{close_id}/confirm", headers=auth_headers)
        pending = client.post(
            f"/api/v1/actions/{close_id}/execute",
            headers=auth_headers,
            json={"ticket": consent.json()["ticket"]},
        )
        assert pending.json()["status"] == "close_pending"

        termination = client.post(
            f"/api/v1/actions/{close_id}/termination", headers=auth_headers
        )
        termination_id = termination.json()["id"]
        first = client.post(
            f"/api/v1/actions/{termination_id}/confirm", headers=auth_headers
        )
        assert first.json()["action"]["status"] == "awaiting_second_confirmation"
        assert first.json()["ticket"] is None
        second = client.post(
            f"/api/v1/actions/{termination_id}/confirm", headers=auth_headers
        )
        completed = client.post(
            f"/api/v1/actions/{termination_id}/execute",
            headers=auth_headers,
            json={"ticket": second.json()["ticket"]},
        )
        assert completed.json()["status"] == "succeeded"
        assert process.terminate_calls == 1
    finally:
        client.app.state.action_coordinator = original
        service.shutdown()
