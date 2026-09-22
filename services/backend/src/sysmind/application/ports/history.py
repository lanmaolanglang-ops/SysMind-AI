from __future__ import annotations

from typing import Protocol

from sysmind.domain.history import (
    BaselineMetric,
    CleanupResult,
    CleanupTrigger,
    DeletionImpact,
    HistoryKind,
)

__all__ = [
    "BaselineMetric",
    "CleanupResult",
    "CleanupTrigger",
    "DeletionImpact",
    "HistoryKind",
    "HistoryRepository",
]


class HistoryRepository(Protocol):
    def impact(self, kind: HistoryKind, record_id: str) -> DeletionImpact | None: ...
    def delete(self, kind: HistoryKind, record_id: str, revision: str) -> bool: ...
    def retention_days(self) -> int: ...
    def set_retention_days(self, days: int) -> int: ...
    def cleanup(self, *, trigger: CleanupTrigger) -> CleanupResult: ...
    def baseline(self) -> tuple[BaselineMetric, ...]: ...
