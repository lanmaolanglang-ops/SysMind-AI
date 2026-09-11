from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import sysmind.application.services.quick_scan as quick_scan_module
from sysmind.api.app import create_app
from sysmind.application.services import QuickScanCoordinator
from sysmind.core.config import Settings
from sysmind.domain.diagnostics import (
    Capability,
    CpuInfo,
    DiskStatus,
    GpuInfo,
    MemoryStatus,
    OperatingSystemInfo,
    ProcessInfo,
)
from sysmind.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    run_migrations,
)
from sysmind.infrastructure.database.repositories import SqlAlchemyScanRepository
from sysmind.tools.contracts import ToolCancelledError, ToolSpec, ToolUnavailableError
from sysmind.tools.process import PROCESS_TOOL_SPECS, ProcessTools
from sysmind.tools.system import SYSTEM_TOOL_SPECS, SystemTools


class FixtureSystemProbe:
    def __init__(self, gpu_available: bool = True) -> None:
        self.gpu_available = gpu_available

    def capabilities(self) -> Sequence[Capability]:
        return (Capability("system.gpu", self.gpu_available),)

    def operating_system(self) -> OperatingSystemInfo:
        return OperatingSystemInfo("Windows", "10.0.26100", "11", "AMD64")

    def cpu(self) -> CpuInfo:
        return CpuInfo("Fixture CPU", 8, 16, 12.5, 4200.0)

    def gpus(self) -> Sequence[GpuInfo]:
        if not self.gpu_available:
            raise ToolUnavailableError("GPU capability is unavailable in this fixture.")
        return (GpuInfo("Fixture GPU", 8_000_000_000, "1.2.3"),)

    def memory(self) -> MemoryStatus:
        return MemoryStatus(16_000, 8_000, 8_000, 50.0)

    def disks(self) -> Sequence[DiskStatus]:
        return (DiskStatus("C:", "C:\\", "NTFS", 100_000, 40_000, 60_000, 60.0),)


class SlowCpuProbe(FixtureSystemProbe):
    def cpu(self) -> CpuInfo:
        time.sleep(0.08)
        return super().cpu()


class FixtureProcessProbe:
    def snapshot(
        self, limit: int = 200, cancel_event: Event | None = None
    ) -> Sequence[ProcessInfo]:
        del limit, cancel_event
        return (ProcessInfo(42, "fixture.exe", 2.0, 2_000, 1.0),)

    def high_usage(
        self,
        cancel_event: Event,
        *,
        sample_seconds: float = 0.5,
        cpu_threshold: float = 25.0,
        memory_threshold: float = 10.0,
        limit: int = 20,
    ) -> Sequence[ProcessInfo]:
        return (ProcessInfo(43, "busy.exe", 55.0, 4_000, 12.0),)


class CancellableProcessProbe(FixtureProcessProbe):
    def high_usage(
        self,
        cancel_event: Event,
        *,
        sample_seconds: float = 0.5,
        cpu_threshold: float = 25.0,
        memory_threshold: float = 10.0,
        limit: int = 20,
    ) -> Sequence[ProcessInfo]:
        if cancel_event.wait(2):
            raise ToolCancelledError("cancelled")
        return ()


def _client(
    settings: Settings,
    gpu_available: bool = True,
    process_probe: FixtureProcessProbe | None = None,
    system_probe: FixtureSystemProbe | None = None,
) -> TestClient:
    repository = SqlAlchemyScanRepository(create_session_factory(settings.database_url))
    coordinator = QuickScanCoordinator(
        repository,
        SystemTools(system_probe or FixtureSystemProbe(gpu_available)),
        ProcessTools(process_probe or FixtureProcessProbe()),
    )
    return TestClient(create_app(settings, quick_scan_coordinator=coordinator))


def _wait_for_terminal(
    client: TestClient, scan_id: str, headers: dict[str, str]
) -> dict[str, object]:
    for _ in range(100):
        payload = client.get(f"/api/v1/scans/{scan_id}", headers=headers).json()
        if payload["status"] in {"completed", "partial", "cancelled", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("scan did not reach a terminal state")


def test_quick_scan_collects_versioned_read_only_snapshot(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    with _client(settings) as client:
        response = client.post("/api/v1/scans/quick", headers=auth_headers)
        assert response.status_code == 202
        payload = _wait_for_terminal(client, response.json()["id"], auth_headers)

        assert payload["status"] == "completed"
        assert payload["schema_version"] == "1.0"
        assert payload["progress"] == 100
        assert payload["summary"]["cpu"]["model"] == "Fixture CPU"
        assert payload["summary"]["high_usage_processes"][0]["name"] == "busy.exe"
        recent = client.get("/api/v1/scans", headers=auth_headers).json()
        assert recent["items"][0]["id"] == payload["id"]

    engine = create_database_engine(settings.database_url)
    with engine.connect() as connection:
        audit_count = connection.execute(
            text("SELECT COUNT(*) FROM scan_step_events WHERE scan_id = :scan_id"),
            {"scan_id": payload["id"]},
        ).scalar_one()
    engine.dispose()
    # One audit row per versioned step; derive the count instead of hardcoding it so adding
    # a tool spec does not break this test.
    assert audit_count == len(SYSTEM_TOOL_SPECS) + len(PROCESS_TOOL_SPECS)


def test_quick_scan_preserves_partial_results_when_capability_is_unavailable(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    with _client(settings, gpu_available=False) as client:
        response = client.post("/api/v1/scans/quick", headers=auth_headers)
        payload = _wait_for_terminal(client, response.json()["id"], auth_headers)

        assert payload["status"] == "partial"
        assert payload["summary"]["memory"]["utilization_percent"] == 50.0
        assert payload["failures"] == [
            {
                "tool": "system.gpu",
                "code": "capability_unavailable",
                "message": "GPU capability is unavailable in this fixture.",
            }
        ]


def test_unknown_scan_returns_not_found(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    with _client(settings) as client:
        response = client.get("/api/v1/scans/missing", headers=auth_headers)
    assert response.status_code == 404


def test_running_scan_can_be_cancelled(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    with _client(settings, process_probe=CancellableProcessProbe()) as client:
        response = client.post("/api/v1/scans/quick", headers=auth_headers)
        scan_id = response.json()["id"]
        for _ in range(100):
            active = client.get(f"/api/v1/scans/{scan_id}", headers=auth_headers).json()
            if active["current_step"] == "process.high_usage":
                break
            time.sleep(0.01)
        cancelled = client.post(f"/api/v1/scans/{scan_id}/cancel", headers=auth_headers)
        assert cancelled.status_code == 200
        payload = _wait_for_terminal(client, scan_id, auth_headers)

        assert payload["status"] == "cancelled"
        assert payload["finished_at"] is not None


def test_timed_out_step_is_mapped_and_other_results_survive(
    settings: Settings,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shortened_specs = tuple(
        ToolSpec(spec.name, spec.version, 0.01 if spec.name == "system.cpu" else 1.0)
        for spec in quick_scan_module.SYSTEM_TOOL_SPECS
    )
    monkeypatch.setattr(quick_scan_module, "SYSTEM_TOOL_SPECS", shortened_specs)

    with _client(settings, system_probe=SlowCpuProbe()) as client:
        response = client.post("/api/v1/scans/quick", headers=auth_headers)
        payload = _wait_for_terminal(client, response.json()["id"], auth_headers)

        assert payload["status"] == "partial"
        assert payload["summary"]["memory"] is not None
        assert {failure["code"] for failure in payload["failures"]} == {"tool_timeout"}


def test_startup_marks_orphaned_scan_as_failed(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    run_migrations(settings.database_url)
    repository = SqlAlchemyScanRepository(create_session_factory(settings.database_url))
    repository.create("orphaned-scan", "2026-08-19T10:00:00+00:00", "1.0")
    repository.update(
        "orphaned-scan",
        status="running",
        progress=40,
        current_step="system.gpu",
    )
    coordinator = QuickScanCoordinator(
        repository,
        SystemTools(FixtureSystemProbe()),
        ProcessTools(FixtureProcessProbe()),
    )

    with TestClient(create_app(settings, quick_scan_coordinator=coordinator)) as client:
        payload = client.get("/api/v1/scans/orphaned-scan", headers=auth_headers).json()

    assert payload["status"] == "failed"
    assert payload["failures"][0]["code"] == "backend_restarted"


@pytest.mark.anyio
async def test_recently_interrupted_scan_is_replayed(settings: Settings) -> None:
    run_migrations(settings.database_url)
    repository = SqlAlchemyScanRepository(create_session_factory(settings.database_url))
    repository.create("replayed-scan", datetime.now(UTC).isoformat(), "1.0")
    repository.update(
        "replayed-scan", status="running", progress=10, current_step="system.gpu"
    )
    coordinator = QuickScanCoordinator(
        repository,
        SystemTools(FixtureSystemProbe()),
        ProcessTools(FixtureProcessProbe()),
    )

    assert coordinator.recover_interrupted() == 1

    record: object = None
    for _ in range(200):
        record = repository.get("replayed-scan")
        if record is not None and record.status in {"completed", "partial"}:
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("the interrupted scan was not replayed")

    assert record is not None
    assert record.status in {"completed", "partial"}
