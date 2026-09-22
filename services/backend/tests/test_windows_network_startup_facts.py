from __future__ import annotations

from sysmind.windows.platform_inspection import (
    _registry_default_gateways,
    _scheduled_startup_task_paths,
)


def test_registry_default_gateways_is_none_off_windows(monkeypatch) -> None:
    monkeypatch.setattr("os.name", "posix")
    assert _registry_default_gateways() is None


def test_scheduled_startup_task_paths_is_none_off_windows(monkeypatch) -> None:
    monkeypatch.setattr("os.name", "posix")
    assert _scheduled_startup_task_paths() is None


def test_scheduled_startup_task_paths_fails_closed_when_collector_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("os.name", "nt")

    def _boom(*_args, **_kwargs):
        raise OSError("collector unavailable")

    monkeypatch.setattr(
        "sysmind.windows.platform_inspection.subprocess.run",
        _boom,
    )
    assert _scheduled_startup_task_paths() is None


def test_scheduled_startup_task_paths_keeps_only_boot_and_logon(monkeypatch) -> None:
    monkeypatch.setattr("os.name", "nt")
    xml = b"""<?xml version="1.0"?>
<Tasks>
  <Task>
    <RegistrationInfo><URI>\\KeepMe</URI></RegistrationInfo>
    <Triggers><BootTrigger/></Triggers>
    <Settings><Enabled>true</Enabled></Settings>
  </Task>
  <Task>
    <RegistrationInfo><URI>\\SkipTime</URI></RegistrationInfo>
    <Triggers><TimeTrigger/></Triggers>
    <Settings><Enabled>true</Enabled></Settings>
  </Task>
  <Task>
    <RegistrationInfo><URI>\\SkipDisabled</URI></RegistrationInfo>
    <Triggers><LogonTrigger/></Triggers>
    <Settings><Enabled>false</Enabled></Settings>
  </Task>
</Tasks>
"""

    class _Result:
        returncode = 0
        stdout = xml

    monkeypatch.setattr(
        "sysmind.windows.platform_inspection.subprocess.run",
        lambda *args, **kwargs: _Result(),
    )
    paths = _scheduled_startup_task_paths()
    assert paths == {"\\KeepMe"}
