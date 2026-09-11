from __future__ import annotations

from collections.abc import Callable
from threading import Event

from sysmind.application.ports.diagnostics import ProcessProbe
from sysmind.tools.contracts import ToolSpec

PROCESS_TOOL_SPECS = (
    ToolSpec("process.snapshot", "1.0", 8.0),
    ToolSpec("process.high_usage", "1.0", 8.0),
)


class ProcessTools:
    """Read-only process collectors driven serially by the first-party scan coordinator.

    Unlike the Tool Registry path, these handlers perform no policy authorization, input
    validation, timeout or result normalization. They are called with fixed arguments and
    must never be dispatched from model output; model-originated calls belong to the
    registry/executor path.
    """

    def __init__(self, probe: ProcessProbe) -> None:
        self._probe = probe

    def handlers(self, cancel_event: Event) -> dict[str, Callable[[], object]]:
        return {
            "process.snapshot": lambda: self._probe.snapshot(cancel_event=cancel_event),
            "process.high_usage": lambda: self._probe.high_usage(cancel_event),
        }
