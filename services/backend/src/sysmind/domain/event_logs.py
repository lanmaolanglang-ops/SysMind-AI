from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

EventLevel: TypeAlias = Literal["critical", "error", "warning", "information"]
LogChannel: TypeAlias = Literal["Application", "System"]
AnalysisStatus: TypeAlias = Literal[
    "queued", "running", "completed", "partial", "cancelled", "failed"
]


# Shared bounds, mirrored by the API DTOs and the tool input model.
MAX_LOOKBACK_HOURS = 168
MAX_EVENTS = 200


@dataclass(frozen=True, slots=True)
class EventLogQuery:
    channel: LogChannel
    lookback_hours: int
    levels: tuple[EventLevel, ...]
    event_ids: tuple[int, ...]
    max_events: int

    def __post_init__(self) -> None:
        # Only the numeric bounds are enforced here. Channel allow-listing is deliberately
        # left to the Windows adapter so a rejected channel still surfaces as an adapter
        # error (defense in depth) rather than a construction failure.
        if not 1 <= self.lookback_hours <= MAX_LOOKBACK_HOURS:
            raise ValueError(f"lookback_hours must be between 1 and {MAX_LOOKBACK_HOURS}.")
        if not 1 <= self.max_events <= MAX_EVENTS:
            raise ValueError(f"max_events must be between 1 and {MAX_EVENTS}.")


@dataclass(frozen=True, slots=True)
class WindowsEvent:
    channel: LogChannel
    provider: str
    event_id: int
    level: EventLevel
    timestamp: str
    summary: str
    application: str | None = None
    faulting_module: str | None = None
    exception_code: str | None = None


@dataclass(frozen=True, slots=True)
class CrashGroup:
    application: str
    faulting_module: str | None
    exception_code: str | None
    count: int
    latest_at: str
    evidence_event_ids: tuple[int, ...]
    providers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EventGroup:
    channel: LogChannel
    provider: str
    event_id: int
    level: EventLevel
    count: int
    latest_at: str
    sample_summary: str


@dataclass(frozen=True, slots=True)
class LogAnalysisRecord:
    id: str
    status: AnalysisStatus
    progress: int
    current_step: str | None
    started_at: str
    finished_at: str | None
    query: dict[str, object]
    summary: dict[str, object] | None
    failures: tuple[dict[str, str], ...]
    schema_version: str

    def __post_init__(self) -> None:
        # `frozen=True` does not deep-freeze containers; copy the mappings so a caller
        # cannot mutate a record that has already been persisted.
        object.__setattr__(self, "query", dict(self.query))
        if self.summary is not None:
            object.__setattr__(self, "summary", dict(self.summary))
