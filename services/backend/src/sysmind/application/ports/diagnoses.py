from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sysmind.domain.diagnosis import (
    DiagnosisCategory,
    DiagnosisHypothesis,
    DiagnosisRecord,
    DiagnosisReport,
    DiagnosisStatus,
    DiagnosisToolCall,
    StopReason,
)


class DiagnosisRepository(Protocol):
    def create(
        self,
        *,
        diagnosis_id: str,
        question: str,
        category: DiagnosisCategory,
        provider: str,
        plan: tuple[dict[str, object], ...],
        created_at: str,
    ) -> DiagnosisRecord: ...
    def get(self, diagnosis_id: str) -> DiagnosisRecord | None: ...
    def recent(self, limit: int = 20) -> list[DiagnosisRecord]: ...
    def update_progress(
        self,
        diagnosis_id: str,
        *,
        status: DiagnosisStatus,
        progress: int,
        current_step: str | None,
        expected_statuses: Sequence[DiagnosisStatus] | None = None,
    ) -> None:
        """Progress write with optional compare-and-set.

        A non-terminal write never revives a terminal diagnosis. With
        ``expected_statuses`` a mismatch raises ``StateConflict``.
        """
        ...
    def save_agent_plan(
        self,
        diagnosis_id: str,
        *,
        provider: str,
        plan: dict[str, object],
        revision: int,
        created_at: str,
    ) -> tuple[str, tuple[str, ...]]:
        """Persist one planner revision and its steps.

        Returns ``(plan_id, step_ids)``: the id of the new plan row, and the created
        step ids in plan order (parallel to ``plan["steps"]``).
        """
        ...
    def finish_diagnosis_step(
        self, step_id: str, *, status: str, tool_call_id: str | None
    ) -> None: ...
    def add_agent_decision(
        self,
        diagnosis_id: str,
        *,
        plan_id: str | None,
        decision_type: str,
        reason: str,
        data: dict[str, object],
        created_at: str,
    ) -> None: ...
    def wait_for_input(self, diagnosis_id: str, *, question: str) -> DiagnosisRecord:
        """Pause for user input. Only valid from queued/running; raises
        ``StateConflict`` otherwise.
        """
        ...
    def resume_with_input(
        self, diagnosis_id: str, *, input_text: str, created_at: str
    ) -> DiagnosisRecord | None: ...
    def user_inputs(self, diagnosis_id: str) -> tuple[str, ...]: ...
    def replace_hypotheses(
        self,
        diagnosis_id: str,
        *,
        hypotheses: tuple[DiagnosisHypothesis, ...],
        updated_at: str,
    ) -> None: ...
    def record_stop_reason(
        self,
        diagnosis_id: str,
        *,
        reason: StopReason,
        detail: str,
        terminal_status: DiagnosisStatus,
        created_at: str,
    ) -> None: ...
    def complete(
        self,
        diagnosis_id: str,
        *,
        status: DiagnosisStatus,
        report: DiagnosisReport,
        markdown: str,
        completed_at: str,
        expected_statuses: Sequence[DiagnosisStatus] | None = None,
    ) -> DiagnosisRecord:
        """Finalize with a report. Loses the race (``StateConflict``) if another
        terminal status already won.
        """
        ...
    def fail(
        self,
        diagnosis_id: str,
        *,
        status: DiagnosisStatus,
        code: str,
        message: str,
        completed_at: str,
        expected_statuses: Sequence[DiagnosisStatus] | None = None,
    ) -> DiagnosisRecord:
        """Finalize with a failure. Loses the race (``StateConflict``) if another
        terminal status already won.
        """
        ...
    def create_tool_call(
        self,
        *,
        call_id: str,
        diagnosis_id: str,
        tool_name: str,
        tool_version: str,
        # Already redacted for audit: raw tool arguments must never reach the repository.
        redacted_arguments: dict[str, object],
        arguments_hash: str,
        started_at: str,
    ) -> None: ...
    def finish_tool_call(
        self,
        call_id: str,
        *,
        status: str,
        result: object | None,
        summary: dict[str, object] | None,
        error_code: str | None,
        error_message: str | None,
        duration_ms: int,
        finished_at: str,
    ) -> None: ...
    def tool_calls(self, diagnosis_id: str) -> tuple[DiagnosisToolCall, ...]: ...
    def add_feedback(
        self, diagnosis_id: str, helpful: bool, comment: str | None, created_at: str
    ) -> None: ...
    def add_model_call(
        self,
        diagnosis_id: str,
        *,
        provider: str,
        status: str,
        request_hash: str,
        response_hash: str | None,
        duration_ms: int,
        error_code: str | None,
        created_at: str,
    ) -> None: ...
    def mark_interrupted(self, completed_at: str) -> int: ...
