from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sysmind.actions import ActionCoordinator
from sysmind.application.ports.actions import ActionVerificationError, StartupActionAdapter
from sysmind.domain.actions import (
    MutationResult,
    ProcessActionCandidate,
    StartupActionCandidate,
)
from sysmind.infrastructure.database import create_session_factory, run_migrations
from sysmind.infrastructure.database.models import (
    Diagnosis,
    DiagnosisToolCallModel,
)
from sysmind.infrastructure.database.repositories import (
    SqlAlchemyActionRepository,
    SqlAlchemyDiagnosisRepository,
)
from sysmind.security import ConsentService
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
    startup_adapter: StartupActionAdapter | None = None,
) -> tuple[ActionCoordinator, StartupActionAdapter]:
    """Build an ActionCoordinator over a seeded SQLite database.

    ``startup_adapter`` is injected at construction so tests never need to overwrite the
    coordinator's private attribute at runtime.
    """
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
                            },
                            {
                                "id": "finding-startup",
                                "code": "startup_inventory",
                                "severity": "low",
                                "title": "startup evidence",
                                "explanation": "evidence",
                                "recommendation": "review",
                                "confidence": 0.7,
                                "evidence": [
                                    {
                                        "tool_call_id": "startup-call",
                                        "field_path": "$.items[0]",
                                    }
                                ],
                            },
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
                result_json=json.dumps(
                    {
                        "items": [
                            {
                                "item_id": "a" * 64,
                                "name": "Example",
                                "source": "user_run",
                            }
                        ]
                    }
                ),
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
                result_json=json.dumps(
                    [{"item_id": "d" * 64, "pid": 4242, "name": "Editor.exe"}]
                ),
                started_at=now,
                finished_at=now,
                duration_ms=1,
            )
        )
    adapter: StartupActionAdapter = startup_adapter or FakeStartupActions()
    return ActionCoordinator(
        SqlAlchemyActionRepository(sessions),
        SqlAlchemyDiagnosisRepository(sessions),
        adapter,
        ConsentService("session"),
        process_adapter,
    ), adapter
