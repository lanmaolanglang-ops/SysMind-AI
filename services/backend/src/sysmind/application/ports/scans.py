from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sysmind.domain.diagnostics import ScanRecord, ScanStatus, StepStatus


class ScanRepository(Protocol):
    def create(self, scan_id: str, started_at: str, schema_version: str) -> ScanRecord: ...

    def update(
        self,
        scan_id: str,
        *,
        status: ScanStatus,
        progress: int,
        current_step: str | None,
        finished_at: str | None = None,
        summary: dict[str, object] | None = None,
        failures: Sequence[dict[str, str]] | None = None,
    ) -> ScanRecord: ...

    def add_step_event(
        self,
        *,
        scan_id: str,
        tool_name: str,
        tool_version: str,
        arguments_hash: str,
        status: StepStatus,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        result_summary: dict[str, object] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    def get(self, scan_id: str) -> ScanRecord | None: ...

    def recent(self, limit: int = 20) -> list[ScanRecord]: ...

    def mark_interrupted(self, finished_at: str) -> int: ...
