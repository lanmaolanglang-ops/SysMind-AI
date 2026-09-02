from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sysmind.domain.actions import (
    ActionCandidate,
    ActionRecord,
    MutationResult,
    ProcessActionCandidate,
    StartupActionCandidate,
)


class TargetChangedError(RuntimeError):
    """The action target no longer matches the evidence-bound revision."""


class ActionVerificationError(RuntimeError):
    """A mutation completed but its post-state could not be verified."""

    def __init__(self, message: str, *, recovery_id: str | None = None) -> None:
        super().__init__(message)
        self.recovery_id = recovery_id


class StartupActionAdapter(Protocol):
    def candidates(self) -> Sequence[StartupActionCandidate]: ...
    def disable(self, item_id: str, observed_revision: str) -> MutationResult: ...
    def restore(self, recovery_id: str) -> MutationResult: ...
    def recovery_exists(self, recovery_id: str) -> bool: ...


class ProcessActionAdapter(Protocol):
    def candidates(self) -> Sequence[ProcessActionCandidate]: ...
    def request_close(self, item_id: str, observed_revision: str) -> MutationResult: ...
    def terminate(self, item_id: str, observed_revision: str) -> MutationResult: ...


class ActionRepository(Protocol):
    def create(
        self,
        *,
        plan_id: str,
        action_id: str,
        diagnosis_id: str,
        tool_name: str,
        target: ActionCandidate,
        created_at: str,
    ) -> ActionRecord: ...
    def create_restore(
        self, *, plan_id: str, action_id: str, original: ActionRecord, created_at: str
    ) -> ActionRecord: ...
    def get(self, action_id: str) -> ActionRecord | None: ...
    def recent(self, limit: int = 20) -> list[ActionRecord]: ...
    def set_status(
        self,
        action_id: str,
        *,
        status: str,
        updated_at: str,
        recovery_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ActionRecord: ...
    def add_confirmation(
        self, action_id: str, *, ticket_digest: str, expires_at: str, created_at: str
    ) -> None: ...
    def add_rejection(self, action_id: str, *, created_at: str) -> None: ...
    def add_confirmation_stage(self, action_id: str, *, stage: int, created_at: str) -> None: ...
    def consume_confirmation(
        self, action_id: str, *, ticket_digest: str, consumed_at: str
    ) -> bool: ...
    def consume_recovery(self, recovery_id: str, *, consumed_at: str) -> None: ...
    def mark_interrupted(self, updated_at: str) -> int: ...
    def close(self) -> None: ...
