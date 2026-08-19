from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

EventLevel: TypeAlias = Literal["critical", "error", "warning", "information"]
LogChannel: TypeAlias = Literal["Application", "System"]
AnalysisStatus: TypeAlias = Literal[
    "queued", "running", "completed", "partial", "cancelled", "failed"
]


@dataclass(frozen=True, slots=True)
class EventLogQuery:
    channel: LogChannel
    lookback_hours: int
    levels: tuple[EventLevel, ...]
    event_ids: tuple[int, ...]
    max_events: int


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
    failures: list[dict[str, str]]
    schema_version: str
