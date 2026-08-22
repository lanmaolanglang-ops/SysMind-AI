from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from sysmind.api.app import create_app
from sysmind.core.config import Settings
from sysmind.infrastructure.database import create_session_factory, run_migrations
from sysmind.infrastructure.database.models import (
    ActionPlanModel,
    DataCleanupRunModel,
    Diagnosis,
    ScanStepEvent,
    SystemScan,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        session_token=SecretStr("history-test-session-token-long-enough"),
    )


def _headers() -> dict[str, str]:
    return {
        "X-SysMind-Session": "history-test-session-token-long-enough",
        "Origin": "tauri://localhost",
    }


def test_deletion_requires_matching_preview_and_cascades_details(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_migrations(settings.database_url)
    sessions = create_session_factory(settings.database_url)
    now = datetime.now(UTC)
    with sessions.begin() as session:
        session.add(
            SystemScan(
                id="scan-delete",
                status="completed",
                progress=100,
                started_at=now,
                finished_at=now,
                failures_json="[]",
                schema_version="1",
            )
        )
        session.flush()
        session.add(
            ScanStepEvent(
                scan_id="scan-delete",
                tool_name="system.cpu",
                tool_version="1",
                status="completed",
                started_at=now,
                finished_at=now,
                duration_ms=1,
            )
        )

    with TestClient(create_app(settings)) as client:
        preview = client.get("/api/v1/history/scan/scan-delete/deletion-impact", headers=_headers())
        stale = client.post(
            "/api/v1/history/scan/scan-delete/delete",
            headers=_headers(),
            json={"revision": "0" * 64},
        )
        deleted = client.post(
            "/api/v1/history/scan/scan-delete/delete",
            headers=_headers(),
            json={"revision": preview.json()["revision"]},
        )

    assert preview.json()["dependent_records"] == 1
    assert stale.status_code == 412
    assert deleted.status_code == 200
    with sessions() as session:
        assert session.get(SystemScan, "scan-delete") is None
        assert session.scalar(select(func.count()).select_from(ScanStepEvent)) == 0
        assert session.scalar(select(func.count()).select_from(DataCleanupRunModel)) >= 2


def test_action_linked_diagnosis_is_protected_from_delete_and_retention(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_migrations(settings.database_url)
    sessions = create_session_factory(settings.database_url)
    old = datetime.now(UTC) - timedelta(days=60)
    with sessions.begin() as session:
        session.add(
            Diagnosis(
                id="diagnosis-protected",
                status="completed",
                user_question="local issue",
                category="general",
                provider="local",
                plan_json="[]",
                progress=100,
                created_at=old,
                completed_at=old,
                schema_version="1",
            )
        )
        session.flush()
        session.add(
            ActionPlanModel(
                id="plan-protected",
                diagnosis_id="diagnosis-protected",
                status="created",
                created_at=old,
            )
        )

    with TestClient(create_app(settings)) as client:
        preview = client.get(
            "/api/v1/history/diagnosis/diagnosis-protected/deletion-impact", headers=_headers()
        )
        cleanup = client.post("/api/v1/history/cleanup", headers=_headers())

    assert preview.json()["deletable"] is False
    assert "audit" in preview.json()["protected_reason"]
    assert cleanup.json()["protected_records"] == 1
    with sessions() as session:
        assert session.get(Diagnosis, "diagnosis-protected") is not None


def test_baseline_uses_completed_scan_medians(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    run_migrations(settings.database_url)
    sessions = create_session_factory(settings.database_url)
    now = datetime.now(UTC)
    with sessions.begin() as session:
        for index, cpu in enumerate((20.0, 40.0)):
            session.add(
                SystemScan(
                    id=f"scan-{index}",
                    status="completed",
                    progress=100,
                    started_at=now - timedelta(minutes=index),
                    finished_at=now,
                    summary_json=json.dumps(
                        {
                            "cpu": {"utilization_percent": cpu},
                            "memory": {"utilization_percent": 50 + index},
                            "disks": [{"utilization_percent": 70 + index}],
                        }
                    ),
                    failures_json="[]",
                    schema_version="1",
                )
            )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/history/baseline", headers=_headers())

    cpu = next(item for item in response.json()["items"] if item["metric"] == "cpu_percent")
    assert cpu == {
        "metric": "cpu_percent",
        "samples": 2,
        "median": 30.0,
        "latest": 20.0,
        "delta": -10.0,
    }
