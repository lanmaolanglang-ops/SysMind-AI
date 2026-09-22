from __future__ import annotations

from pathlib import Path

import pytest

from sysmind.application.ports.state_conflict import StateConflict
from sysmind.domain.diagnosis import DiagnosisReport
from sysmind.infrastructure.database import create_session_factory, run_migrations
from sysmind.infrastructure.database.models import ActionPlanModel, DiagnosisToolCallModel
from sysmind.infrastructure.database.repositories import (
    SqlAlchemyAgentTaskRepository,
    SqlAlchemyDiagnosisRepository,
    SqlAlchemyHistoryRepository,
    SqlAlchemyLogAnalysisRepository,
    SqlAlchemyScanRepository,
)


@pytest.fixture
def sessions(tmp_path: Path):
    database_url = f"sqlite:///{(tmp_path / 'cas.db').as_posix()}"
    run_migrations(database_url)
    return create_session_factory(database_url)


def _empty_report() -> DiagnosisReport:
    return DiagnosisReport(
        "1.0",
        "summary",
        "performance",
        (),
        0.5,
        (),
        "explanation",
        (),
    )


def test_scan_terminal_statuses_do_not_overwrite_each_other(sessions) -> None:
    repo = SqlAlchemyScanRepository(sessions)
    repo.create("scan-1", "2026-09-22T10:00:00+00:00", "1.0")
    repo.update(
        "scan-1",
        status="running",
        progress=10,
        current_step="system.cpu",
        expected_statuses=("queued", "running"),
    )
    cancelled = repo.update(
        "scan-1",
        status="cancelled",
        progress=20,
        current_step=None,
        finished_at="2026-09-22T10:00:05+00:00",
        expected_statuses=("queued", "running"),
    )
    assert cancelled.status == "cancelled"

    with pytest.raises(StateConflict):
        repo.update(
            "scan-1",
            status="completed",
            progress=100,
            current_step=None,
            finished_at="2026-09-22T10:00:06+00:00",
            expected_statuses=("queued", "running"),
        )

    # Implicit CAS: a second different terminal write must also lose.
    with pytest.raises(StateConflict):
        repo.update(
            "scan-1",
            status="completed",
            progress=100,
            current_step=None,
            finished_at="2026-09-22T10:00:07+00:00",
        )
    assert repo.get("scan-1").status == "cancelled"


def test_scan_progress_cannot_revive_terminal(sessions) -> None:
    repo = SqlAlchemyScanRepository(sessions)
    repo.create("scan-2", "2026-09-22T10:00:00+00:00", "1.0")
    repo.update(
        "scan-2",
        status="cancelled",
        progress=5,
        current_step=None,
        finished_at="2026-09-22T10:00:01+00:00",
        expected_statuses=("queued", "running"),
    )
    # Late progress write is a silent no-op and must not raise or revive.
    result = repo.update(
        "scan-2",
        status="running",
        progress=50,
        current_step="late",
    )
    assert result.status == "cancelled"
    assert result.current_step is None


def test_scan_idempotent_same_terminal_rewrite(sessions) -> None:
    repo = SqlAlchemyScanRepository(sessions)
    repo.create("scan-3", "2026-09-22T10:00:00+00:00", "1.0")
    first = repo.update(
        "scan-3",
        status="failed",
        progress=10,
        current_step=None,
        finished_at="2026-09-22T10:00:01+00:00",
        failures=[{"tool": "scan", "code": "x", "message": "y"}],
        expected_statuses=("queued", "running"),
    )
    assert first.status == "failed"
    second = repo.update(
        "scan-3",
        status="failed",
        progress=10,
        current_step=None,
        finished_at="2026-09-22T10:00:02+00:00",
    )
    assert second.status == "failed"


def test_log_analysis_terminal_exclusive(sessions) -> None:
    repo = SqlAlchemyLogAnalysisRepository(sessions)
    repo.create(
        "log-1",
        "2026-09-22T10:00:00+00:00",
        {
            "channel": "Application",
            "lookback_hours": 1,
            "levels": (),
            "event_ids": (),
            "max_events": 10,
        },
        "1.0",
    )
    repo.update(
        "log-1",
        status="cancelled",
        progress=0,
        current_step=None,
        finished_at="2026-09-22T10:00:01+00:00",
        expected_statuses=("queued", "running"),
    )
    with pytest.raises(StateConflict):
        repo.update(
            "log-1",
            status="completed",
            progress=100,
            current_step=None,
            finished_at="2026-09-22T10:00:02+00:00",
            expected_statuses=("queued", "running"),
        )
    assert repo.get("log-1").status == "cancelled"


def test_agent_task_complete_vs_cancel_single_winner(sessions) -> None:
    from sysmind.domain.agent_tasks import AgentBudget

    repo = SqlAlchemyAgentTaskRepository(sessions)
    repo.create(
        task_id="task-1",
        user_goal="why slow",
        provider="fake",
        allowed_tools=("system.cpu@1.0",),
        budget=AgentBudget(max_rounds=1, max_tool_calls=1, timeout_seconds=5.0),
        created_at="2026-09-22T10:00:00+00:00",
        schema_version="1.0",
    )
    repo.request_cancel("task-1")
    assert repo.get("task-1").status == "cancelling"

    completed = repo.update(
        "task-1",
        status="completed",
        current_round=1,
        tool_call_count=0,
        progress=100,
        working_summary={},
        finished_at="2026-09-22T10:00:01+00:00",
        final_output="done",
        expected_statuses=("created", "planning", "running_tools", "analyzing", "cancelling"),
    )
    assert completed.status == "completed"

    with pytest.raises(StateConflict):
        repo.update(
            "task-1",
            status="cancelled",
            current_round=1,
            tool_call_count=0,
            progress=100,
            working_summary={},
            finished_at="2026-09-22T10:00:02+00:00",
            failure_code="cancelled",
            failure_message="cancelled",
            expected_statuses=("created", "planning", "running_tools", "analyzing", "cancelling"),
        )
    assert repo.get("task-1").status == "completed"


def test_agent_task_cancel_does_not_revive_terminal(sessions) -> None:
    from sysmind.domain.agent_tasks import AgentBudget

    repo = SqlAlchemyAgentTaskRepository(sessions)
    repo.create(
        task_id="task-2",
        user_goal="why slow",
        provider="fake",
        allowed_tools=(),
        budget=AgentBudget(max_rounds=1, max_tool_calls=1, timeout_seconds=5.0),
        created_at="2026-09-22T10:00:00+00:00",
        schema_version="1.0",
    )
    repo.update(
        "task-2",
        status="completed",
        current_round=1,
        tool_call_count=0,
        progress=100,
        working_summary={},
        finished_at="2026-09-22T10:00:01+00:00",
    )
    record = repo.request_cancel("task-2")
    assert record is not None
    assert record.status == "completed"
    assert record.cancel_requested is True


def test_diagnosis_complete_vs_fail_single_winner(sessions) -> None:
    repo = SqlAlchemyDiagnosisRepository(sessions)
    repo.create(
        diagnosis_id="diag-1",
        question="电脑很卡",
        category="performance",
        provider="local",
        plan=(),
        created_at="2026-09-22T10:00:00+00:00",
    )
    failed = repo.fail(
        "diag-1",
        status="cancelled",
        code="cancelled",
        message="诊断已取消。",
        completed_at="2026-09-22T10:00:01+00:00",
    )
    assert failed.status == "cancelled"

    with pytest.raises(StateConflict):
        repo.complete(
            "diag-1",
            status="completed",
            report=_empty_report(),
            markdown="# report",
            completed_at="2026-09-22T10:00:02+00:00",
        )
    assert repo.get("diag-1").status == "cancelled"


def test_diagnosis_wait_for_input_requires_active_status(sessions) -> None:
    repo = SqlAlchemyDiagnosisRepository(sessions)
    repo.create(
        diagnosis_id="diag-2",
        question="电脑很卡",
        category="performance",
        provider="local",
        plan=(),
        created_at="2026-09-22T10:00:00+00:00",
    )
    with pytest.raises(StateConflict):
        # queued is active; force a terminal first.
        repo.fail(
            "diag-2",
            status="failed",
            code="internal_error",
            message="x",
            completed_at="2026-09-22T10:00:01+00:00",
        )
        repo.wait_for_input("diag-2", question="more?")
    assert repo.get("diag-2").status == "failed"


def test_history_delete_rejects_stale_revision(sessions) -> None:
    scan_repo = SqlAlchemyScanRepository(sessions)
    history = SqlAlchemyHistoryRepository(sessions)
    scan_repo.create("scan-h", "2026-09-22T10:00:00+00:00", "1.0")
    scan_repo.update(
        "scan-h",
        status="completed",
        progress=100,
        current_step=None,
        finished_at="2026-09-22T10:00:01+00:00",
        summary={"cpu": {"utilization_percent": 1}},
        expected_statuses=("queued", "running"),
    )
    preview = history.impact("scan", "scan-h")
    assert preview is not None and preview.deletable

    # A new dependent row changes the impact revision after the preview.
    with sessions.begin() as session:
        from sysmind.infrastructure.database.models import ScanStepEvent

        session.add(
            ScanStepEvent(
                scan_id="scan-h",
                tool_name="system.cpu",
                tool_version="1.0",
                arguments_hash="abc",
                status="completed",
                started_at=__import__("datetime").datetime.fromisoformat(
                    "2026-09-22T10:00:02+00:00"
                ),
                finished_at=__import__("datetime").datetime.fromisoformat(
                    "2026-09-22T10:00:03+00:00"
                ),
                duration_ms=1,
            )
        )

    assert history.delete("scan", "scan-h", preview.revision) is False
    with sessions() as session:
        from sysmind.infrastructure.database.models import SystemScan

        assert session.get(SystemScan, "scan-h") is not None

    fresh = history.impact("scan", "scan-h")
    assert fresh is not None and fresh.revision != preview.revision
    assert history.delete("scan", "scan-h", fresh.revision) is True


def test_history_delete_rejects_when_action_audit_appears(sessions) -> None:
    from datetime import datetime

    repo = SqlAlchemyDiagnosisRepository(sessions)
    history = SqlAlchemyHistoryRepository(sessions)
    repo.create(
        diagnosis_id="diag-h",
        question="电脑很卡",
        category="performance",
        provider="local",
        plan=(),
        created_at="2026-09-22T10:00:00+00:00",
    )
    repo.complete(
        "diag-h",
        status="completed",
        report=_empty_report(),
        markdown="# ok",
        completed_at="2026-09-22T10:00:01+00:00",
    )
    preview = history.impact("diagnosis", "diag-h")
    assert preview is not None and preview.deletable

    with sessions.begin() as session:
        session.add(
            ActionPlanModel(
                id="plan-h",
                diagnosis_id="diag-h",
                status="proposed",
                created_at=datetime.fromisoformat("2026-09-22T10:00:02+00:00"),
            )
        )

    assert history.delete("diagnosis", "diag-h", preview.revision) is False
    with sessions() as session:
        from sysmind.infrastructure.database.models import Diagnosis

        assert session.get(Diagnosis, "diag-h") is not None
        assert session.get(ActionPlanModel, "plan-h") is not None


def test_history_delete_cascades_tool_calls_with_rowcount(sessions) -> None:

    repo = SqlAlchemyDiagnosisRepository(sessions)
    history = SqlAlchemyHistoryRepository(sessions)
    repo.create(
        diagnosis_id="diag-c",
        question="电脑很卡",
        category="performance",
        provider="local",
        plan=(),
        created_at="2026-09-22T10:00:00+00:00",
    )
    repo.complete(
        "diag-c",
        status="completed",
        report=_empty_report(),
        markdown="# ok",
        completed_at="2026-09-22T10:00:01+00:00",
    )
    repo.create_tool_call(
        call_id="call-c",
        diagnosis_id="diag-c",
        tool_name="system.cpu",
        tool_version="1.0",
        redacted_arguments={},
        arguments_hash="abc",
        started_at="2026-09-22T10:00:02+00:00",
    )
    preview = history.impact("diagnosis", "diag-c")
    assert preview is not None and preview.dependent_records >= 1
    assert history.delete("diagnosis", "diag-c", preview.revision) is True
    with sessions() as session:
        from sysmind.infrastructure.database.models import Diagnosis

        assert session.get(Diagnosis, "diag-c") is None
        assert session.get(DiagnosisToolCallModel, "call-c") is None
