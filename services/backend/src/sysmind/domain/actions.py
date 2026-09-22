from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
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
MutationOutcome: TypeAlias = Literal["succeeded", "closed", "close_pending", "terminated"]

# Controlled-action tools are driven by the ActionCoordinator rather than the read-only
# Tool Registry, so their canonical names and versions are defined here. Keeping both in
# one place stops audit records (tool_name/tool_version) and call sites from drifting.
DISABLE_STARTUP_TOOL = "startup.disable_current_user"
RESTORE_STARTUP_TOOL = "startup.restore_current_user"
CLOSE_PROCESS_TOOL = "process.request_close_current_user"
TERMINATE_PROCESS_TOOL = "process.terminate_current_user"

# Read-only view: versions are part of the audit contract and must not drift at runtime.
ACTION_TOOL_VERSIONS: Mapping[str, str] = MappingProxyType(
    {
        DISABLE_STARTUP_TOOL: "1.0",
        RESTORE_STARTUP_TOOL: "1.0",
        CLOSE_PROCESS_TOOL: "1.0",
        TERMINATE_PROCESS_TOOL: "1.0",
    }
)


def action_tool_version(tool_name: str) -> str:
    """Return the canonical audit version for a controlled-action tool.

    Unregistered tools raise instead of inventing ``1.0`` so action audit rows can
    never record a fabricated version.
    """
    try:
        return ACTION_TOOL_VERSIONS[tool_name]
    except KeyError:
        raise KeyError(
            f"Unregistered action tool {tool_name!r}; refusing to invent a tool version."
        ) from None


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
    outcome: MutationOutcome = "succeeded"
