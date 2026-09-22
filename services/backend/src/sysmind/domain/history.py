from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

HistoryKind = Literal["scan", "diagnosis", "log"]
# Allowed audit reasons for a bulk retention cleanup run.
CleanupTrigger: TypeAlias = Literal["manual", "startup", "retention"]


@dataclass(frozen=True, slots=True)
class DeletionImpact:
    kind: HistoryKind
    record_id: str
    revision: str
    deletable: bool
    dependent_records: int
    protected_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CleanupResult:
    deleted_scans: int
    deleted_diagnoses: int
    deleted_log_analyses: int
    protected_records: int
    completed_at: str


@dataclass(frozen=True, slots=True)
class BaselineMetric:
    metric: str
    samples: int
    median: float
    latest: float
    delta: float
