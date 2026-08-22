from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

HistoryKind = Literal["scan", "diagnosis", "log"]


@dataclass(frozen=True)
class DeletionImpact:
    kind: HistoryKind
    record_id: str
    revision: str
    deletable: bool
    dependent_records: int
    protected_reason: str | None = None


@dataclass(frozen=True)
class CleanupResult:
    deleted_scans: int
    deleted_diagnoses: int
    deleted_log_analyses: int
    protected_records: int
    completed_at: str


@dataclass(frozen=True)
class BaselineMetric:
    metric: str
    samples: int
    median: float
    latest: float
    delta: float


class HistoryRepository(Protocol):
    def impact(self, kind: HistoryKind, record_id: str) -> DeletionImpact | None: ...
    def delete(self, kind: HistoryKind, record_id: str, revision: str) -> bool: ...
    def retention_days(self) -> int: ...
    def set_retention_days(self, days: int) -> int: ...
    def cleanup(self, *, trigger: str) -> CleanupResult: ...
    def baseline(self) -> tuple[BaselineMetric, ...]: ...
