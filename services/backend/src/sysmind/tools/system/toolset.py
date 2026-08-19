from __future__ import annotations

from collections.abc import Callable, Sequence

from sysmind.application.ports.diagnostics import SystemProbe
from sysmind.domain.diagnostics import Capability
from sysmind.tools.contracts import ToolSpec

SYSTEM_TOOL_SPECS = (
    ToolSpec("system.os", "1.0", 3.0),
    ToolSpec("system.cpu", "1.0", 3.0),
    ToolSpec("system.gpu", "1.0", 8.0),
    ToolSpec("system.memory", "1.0", 3.0),
    ToolSpec("system.disks", "1.0", 5.0),
)


class SystemTools:
    """Versioned read-only system collectors; this is not the Phase 3 Agent registry."""

    def __init__(self, probe: SystemProbe) -> None:
        self._probe = probe

    def capabilities(self) -> Sequence[Capability]:
        return self._probe.capabilities()

    def handlers(self) -> dict[str, Callable[[], object]]:
        return {
            "system.os": self._probe.operating_system,
            "system.cpu": self._probe.cpu,
            "system.gpu": self._probe.gpus,
            "system.memory": self._probe.memory,
            "system.disks": self._probe.disks,
        }
