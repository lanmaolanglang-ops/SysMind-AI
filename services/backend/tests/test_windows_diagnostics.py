from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from sysmind.api.app import create_app
from sysmind.core.config import Settings
from sysmind.windows.diagnostics import (
    WindowsProcessProbe,
    WindowsSystemProbe,
    _normalized_cpu_percent,
)


def test_process_cpu_is_normalized_to_whole_machine_percentage() -> None:
    assert _normalized_cpu_percent(1600.0, logical_cores=32) == 50.0
    assert _normalized_cpu_percent(6400.0, logical_cores=32) == 100.0


def test_gpu_parser_uses_fixed_application_command(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[-1].startswith("Get-CimInstance Win32_VideoController")
        return subprocess.CompletedProcess(
            command,
            0,
            '[{"Name":"Fixture GPU","AdapterRAM":4096,"DriverVersion":"9.1"}]',
            "",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = WindowsSystemProbe(powershell_path="powershell.exe").gpus()

    assert result[0].name == "Fixture GPU"
    assert result[0].memory_bytes == 4096


@pytest.mark.windows_smoke
@pytest.mark.skipif(sys.platform != "win32", reason="Windows adapter smoke test")
def test_windows_read_only_adapter_smoke() -> None:
    system = WindowsSystemProbe()
    processes = WindowsProcessProbe()

    assert system.operating_system().name == "Windows"
    assert system.cpu().logical_cores > 0
    assert system.memory().total_bytes > 0
    assert system.disks()
    assert processes.snapshot(limit=5)


@pytest.mark.windows_smoke
@pytest.mark.skipif(sys.platform != "win32", reason="Windows quick scan smoke test")
def test_windows_quick_scan_api_smoke(tmp_path: Path) -> None:
    token = "windows-smoke-session-token-long-enough"
    settings = Settings(data_dir=tmp_path, session_token=SecretStr(token))
    headers = {"X-SysMind-Session": token, "Origin": "tauri://localhost"}

    with TestClient(create_app(settings)) as client:
        response = client.post("/api/v1/scans/quick", headers=headers)
        assert response.status_code == 202
        scan_id = response.json()["id"]
        for _ in range(160):
            payload = client.get(f"/api/v1/scans/{scan_id}", headers=headers).json()
            if payload["status"] in {"completed", "partial"}:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("real Windows quick scan did not finish")

    assert payload["summary"]["operating_system"]["name"] == "Windows"
    assert payload["summary"]["cpu"]["logical_cores"] > 0
    assert payload["summary"]["memory"]["total_bytes"] > 0
