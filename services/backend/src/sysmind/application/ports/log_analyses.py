from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sysmind.domain.diagnostics import StepStatus
from sysmind.domain.event_logs import AnalysisStatus, LogAnalysisRecord


class LogAnalysisRepository(Protocol):
    def create(
        self, analysis_id: str, started_at: str, query: dict[str, object], schema_version: str
    ) -> LogAnalysisRecord: ...

    def update(
        self,
        analysis_id: str,
        *,
        status: AnalysisStatus,
        progress: int,
        current_step: str | None,
        finished_at: str | None = None,
        summary: dict[str, object] | None = None,
        failures: Sequence[dict[str, str]] | None = None,
    ) -> LogAnalysisRecord: ...

    def add_step_event(
        self,
        *,
        analysis_id: str,
        tool_name: str,
        tool_version: str,
        status: StepStatus,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        arguments_hash: str,
        result_summary: dict[str, object] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    def get(self, analysis_id: str) -> LogAnalysisRecord | None: ...

    def recent(self, limit: int = 20) -> list[LogAnalysisRecord]: ...

    def mark_interrupted(self, finished_at: str) -> int: ...
