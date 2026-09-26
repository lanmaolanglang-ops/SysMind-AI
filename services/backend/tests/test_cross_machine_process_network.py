from __future__ import annotations

import asyncio
from threading import Event
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter

from sysmind.agent.planning import FakeDiagnosisPlanner
from sysmind.tools.registry import ToolDefinition, ToolRegistry
from sysmind.windows.diagnostics import WindowsProcessProbe


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _FakeProc:
    def __init__(self, pid: int, *, denied: bool = False, vanish: bool = False) -> None:
        self.pid = pid
        self._denied = denied
        self._vanish = vanish

    def cpu_percent(self, interval: Any = None) -> float:
        if self._vanish:
            import psutil

            raise psutil.NoSuchProcess(self.pid)
        if self._denied:
            import psutil

            raise psutil.AccessDenied(self.pid)
        return 1.0

    def memory_info(self) -> Any:
        return SimpleNamespace(rss=1024 * self.pid)

    def create_time(self) -> float:
        return 1_700_000_000.0

    def name(self) -> str:
        return f"proc-{self.pid}"

    def memory_percent(self) -> float:
        return 1.0


def test_snapshot_isolates_denied_and_vanished(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = WindowsProcessProbe()
    procs = [
        _FakeProc(1),
        _FakeProc(2, denied=True),
        _FakeProc(3, vanish=True),
        _FakeProc(4),
    ]
    monkeypatch.setattr(
        "sysmind.windows.diagnostics.psutil.process_iter",
        lambda: iter(procs),
    )
    items = probe.snapshot(limit=10, cancel_event=Event(), sample_seconds=0.0)
    assert {item.pid for item in items} == {1, 4}


def test_snapshot_budget_expiry_keeps_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = WindowsProcessProbe()
    monkeypatch.setattr(
        "sysmind.windows.diagnostics.psutil.process_iter",
        lambda: iter([_FakeProc(1), _FakeProc(2)]),
    )
    monkeypatch.setattr(WindowsProcessProbe, "_COLLECTION_BUDGET_SECONDS", 0.0)
    items = probe.snapshot(limit=10, cancel_event=Event(), sample_seconds=0.0)
    assert isinstance(items, tuple)


def test_snapshot_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    from sysmind.tools.contracts import ToolCancelledError

    probe = WindowsProcessProbe()
    monkeypatch.setattr(
        "sysmind.windows.diagnostics.psutil.process_iter",
        lambda: iter([_FakeProc(1)]),
    )
    cancel = Event()
    cancel.set()
    with pytest.raises(ToolCancelledError):
        probe.snapshot(limit=5, cancel_event=cancel, sample_seconds=0.0)


def _registry() -> ToolRegistry:
    names = (
        "system.cpu",
        "system.memory",
        "system.disks",
        "system.gpu",
        "process.snapshot",
        "process.high_usage",
        "startup.analyze",
        "network.proxy.get_config",
        "network.diagnose",
        "log.crash.analyze",
    )
    definitions = []
    for name in names:
        risk = "network" if name.startswith("network.") else "read_only"
        definitions.append(
            ToolDefinition(
                name=name,
                version="1.0",
                description=f"Bounded test collector for {name}.",
                input_model=EmptyInput,
                output_adapter=TypeAdapter(dict[str, object]),
                risk_level=risk,
                required_privilege="user",
                sensitivity=(),
                timeout_seconds=1,
                concurrency_key=name,
                confirmation_policy="none",
                handler=lambda _input, _cancel: {},
                summarizer=lambda value: value,
            )
        )
    return ToolRegistry(tuple(definitions))


def test_network_intent_selects_network_tools() -> None:
    async def _run() -> None:
        planner = FakeDiagnosisPlanner(_registry())
        for question in (
            "无法上网",
            "网络断了",
            "Wi-Fi 正常但打不开网页",
            "默认网关是不是有问题",
            "IPv6 有问题吗",
        ):
            plan = await planner.create_plan(question)
            tools = [step.tool for step in plan.steps]
            assert any(tool.startswith("network.") for tool in tools), question

    asyncio.run(_run())


def test_performance_intent_keeps_performance_tools() -> None:
    async def _run() -> None:
        planner = FakeDiagnosisPlanner(_registry())
        plan = await planner.create_plan("电脑很慢")
        tools = [step.tool for step in plan.steps]
        assert "system.cpu@1.0" in tools
        assert not any(tool.startswith("network.") for tool in tools)

    asyncio.run(_run())
