from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

ActionStatus: TypeAlias = Literal[
    "proposed",
    "rejected",
    "awaiting_second_confirmation",
    "confirmed",
    "executing",
    "verifying",
    "succeeded",
    "failed",
    "verification_failed",
    "expired",
    "target_changed",
    "close_pending",
    "interrupted",
]
StartupSourceKind: TypeAlias = Literal["user_run", "user_startup"]


@dataclass(frozen=True, slots=True)
class StartupActionCandidate:
    item_id: str
    name: str
    source_kind: StartupSourceKind
    command_name: str | None
    observed_revision: str


@dataclass(frozen=True, slots=True)
class ProcessActionCandidate:
    item_id: str
    name: str
    source_kind: Literal["current_user_process"]
    command_name: str | None
    observed_revision: str
    pid: int
    cpu_percent: float
    memory_percent: float


ActionCandidate: TypeAlias = StartupActionCandidate | ProcessActionCandidate


@dataclass(frozen=True, slots=True)
class ActionRecord:
    id: str
    plan_id: str
    diagnosis_id: str
    tool_name: str
    tool_version: str
    target_id: str
    target_name: str
    source_kind: str
    observed_revision: str
    status: ActionStatus
    recovery_id: str | None
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class MutationResult:
    recovery_id: str | None
    verified_revision: str | None
    outcome: str = "succeeded"
