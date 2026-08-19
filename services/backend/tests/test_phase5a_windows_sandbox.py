from __future__ import annotations

import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest

from sysmind.actions import ActionCoordinator
from sysmind.infrastructure.database import create_session_factory, run_migrations
from sysmind.infrastructure.database.models import Diagnosis, DiagnosisToolCallModel
from sysmind.infrastructure.database.repositories import (
    SqlAlchemyActionRepository,
    SqlAlchemyDiagnosisRepository,
)
from sysmind.security import ConsentService
from sysmind.windows.process_actions import WindowsProcessActionAdapter
from sysmind.windows.startup_actions import TargetChangedError, WindowsStartupActionAdapter

_ACK = "SYSMIND_PHASE5A_ISOLATED_TEST_ONLY"
_VM_MARKER = Path(r"C:\SysMind-Isolated-Test-VM.marker")
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _isolated_environment() -> bool:
    sandbox_user = os.getenv("USERNAME", "").casefold() == "wdagutilityaccount"
    marked_vm = _VM_MARKER.is_file()
    return (
        os.name == "nt"
        and os.getenv("SYSMIND_DESTRUCTIVE_SANDBOX") == _ACK
        and (sandbox_user or marked_vm)
    )


pytestmark = [
    pytest.mark.destructive_sandbox,
    pytest.mark.skipif(
        not _isolated_environment(),
        reason="requires explicit acknowledgement inside Windows Sandbox or a marked disposable VM",
    ),
]


def _delete_run_value(name: str) -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except OSError:
        pass


def _coordinator(tmp_path: Path, adapter: WindowsStartupActionAdapter) -> ActionCoordinator:
    database_url = f"sqlite:///{(tmp_path / 'actions.db').as_posix()}"
    run_migrations(database_url)
    sessions = create_session_factory(database_url)
    now = datetime.now(UTC)
    diagnosis_id = "00000000-0000-4000-8000-000000000005"
    with sessions.begin() as session:
        session.add(
            Diagnosis(
                id=diagnosis_id,
                status="completed",
                user_question="检查启动项",
                category="performance",
                provider="local-rules",
                plan_json="[]",
                progress=100,
                created_at=now,
                completed_at=now,
                schema_version="1.0",
            )
        )
        session.add(
            DiagnosisToolCallModel(
                id="00000000-0000-4000-8000-000000000006",
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
    return ActionCoordinator(
        SqlAlchemyActionRepository(sessions),
        SqlAlchemyDiagnosisRepository(sessions),
        adapter,
        ConsentService("isolated-test-session"),
    )


def test_real_hkcu_run_disable_restore_revision_and_conflict(tmp_path: Path) -> None:
    import winreg

    name = f"SysMindPhase5ATest-{uuid.uuid4()}"
    command = r'"C:\Windows\System32\cmd.exe" /c exit 0'
    adapter = WindowsStartupActionAdapter(tmp_path / "recovery")
    service = _coordinator(tmp_path, adapter)
    _delete_run_value(name)
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
        candidate = next(item for item in adapter.candidates() if item.name == name)

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command + " changed")
        with pytest.raises(TargetChangedError):
            adapter.disable(candidate.item_id, candidate.observed_revision)

        current = next(
            item
            for item in service.candidates("00000000-0000-4000-8000-000000000005")
            if item.name == name
        )
        action = service.create_disable(
            "00000000-0000-4000-8000-000000000005",
            current.item_id,
            current.observed_revision,
        )
        _confirmed, ticket, _expires = service.confirm(action.id)
        disabled = service.execute(action.id, ticket)
        assert disabled.status == "succeeded"
        assert disabled.recovery_id is not None
        assert all(item.name != name for item in adapter.candidates())

        conflict_restore = service.create_restore(disabled.id)
        _confirmed, conflict_ticket, _expires = service.confirm(conflict_restore.id)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, "replacement")
        conflict = service.execute(conflict_restore.id, conflict_ticket)
        assert conflict.status == "target_changed"
        _delete_run_value(name)

        restore = service.create_restore(disabled.id)
        _confirmed, restore_ticket, _expires = service.confirm(restore.id)
        restored = service.execute(restore.id, restore_ticket)
        assert restored.status == "succeeded"
        assert any(item.name == name for item in adapter.candidates())
        assert not adapter.recovery_exists(disabled.recovery_id)
    finally:
        _delete_run_value(name)
        service.shutdown()


def test_real_current_user_startup_file_disable_and_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appdata = tmp_path / "appdata"
    startup = appdata / "Microsoft/Windows/Start Menu/Programs/Startup"
    startup.mkdir(parents=True)
    entry = startup / f"SysMindPhase5ATest-{uuid.uuid4()}.cmd"
    entry.write_text("@exit /b 0\n", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    adapter = WindowsStartupActionAdapter(tmp_path / "recovery")

    candidate = next(item for item in adapter.candidates() if item.command_name == entry.name)
    disabled = adapter.disable(candidate.item_id, candidate.observed_revision)
    assert disabled.recovery_id is not None
    assert not entry.exists()
    assert adapter.recovery_exists(disabled.recovery_id)

    adapter.restore(disabled.recovery_id)
    assert entry.read_text(encoding="utf-8") == "@exit /b 0\n"
    assert not adapter.recovery_exists(disabled.recovery_id)


def test_real_gui_process_receives_only_bounded_close_request() -> None:
    before = {
        process.pid
        for process in psutil.process_iter(("name",))
        if str(process.info.get("name") or "").casefold() == "notepad.exe"
    }
    subprocess.run(
        ["explorer.exe", "notepad.exe"],
        check=False,
        timeout=5,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    adapter = WindowsProcessActionAdapter(close_wait_seconds=8.0)
    candidate = None
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and candidate is None:
        candidate = next(
            (
                item
                for item in adapter.candidates()
                if item.name.casefold() == "notepad.exe" and item.pid not in before
            ),
            None,
        )
        time.sleep(0.2)
    if candidate is None:
        pytest.fail("Disposable VM did not expose the test Notepad window as an eligible process.")
    try:
        result = adapter.request_close(candidate.item_id, candidate.observed_revision)
        assert result.outcome == "closed"
    finally:
        try:
            remaining = psutil.Process(candidate.pid)
            if remaining.create_time() and remaining.is_running():
                remaining.terminate()
                remaining.wait(3)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass


def test_real_gui_forced_termination_requires_prior_pending_close(tmp_path: Path) -> None:
    script = tmp_path / "phase5_ignore_close.pyw"
    pid_file = tmp_path / "phase5_gui.pid"
    script.write_text(
        "import os, tkinter as tk\n"
        f"open({str(pid_file)!r}, 'w', encoding='utf-8').write(str(os.getpid()))\n"
        "root = tk.Tk()\n"
        "root.title('SysMind Phase 5 isolated termination target')\n"
        "root.protocol('WM_DELETE_WINDOW', lambda: None)\n"
        "root.mainloop()\n",
        encoding="utf-8",
    )
    os.startfile(script)  # type: ignore[attr-defined]
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not pid_file.exists():
        time.sleep(0.1)
    assert pid_file.exists(), "Isolated GUI test process did not start."
    pid = int(pid_file.read_text(encoding="utf-8"))
    adapter = WindowsProcessActionAdapter(close_wait_seconds=0.5)
    candidate = None
    while time.monotonic() < deadline and candidate is None:
        candidate = next((item for item in adapter.candidates() if item.pid == pid), None)
        time.sleep(0.1)
    if candidate is None:
        pytest.fail("Isolated GUI target did not pass the process protection policy.")
    try:
        pending = adapter.request_close(candidate.item_id, candidate.observed_revision)
        assert pending.outcome == "close_pending"
        refreshed = next(item for item in adapter.candidates() if item.item_id == candidate.item_id)
        terminated = adapter.terminate(refreshed.item_id, refreshed.observed_revision)
        assert terminated.outcome == "terminated"
    finally:
        try:
            remaining = psutil.Process(pid)
            remaining.terminate()
            remaining.wait(3)
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass
