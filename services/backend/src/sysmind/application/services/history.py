from __future__ import annotations

from sysmind.application.ports.history import (
    BaselineMetric,
    CleanupResult,
    DeletionImpact,
    HistoryKind,
    HistoryRepository,
)


class HistoryChangedError(RuntimeError):
    pass


class HistoryProtectedError(RuntimeError):
    pass


class HistoryService:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repository = repository

    def impact(self, kind: HistoryKind, record_id: str) -> DeletionImpact | None:
        return self._repository.impact(kind, record_id)

    def delete(self, kind: HistoryKind, record_id: str, revision: str) -> None:
        impact = self._repository.impact(kind, record_id)
        if impact is None:
            raise LookupError(record_id)
        if not impact.deletable:
            raise HistoryProtectedError(impact.protected_reason or "Record is protected.")
        if impact.revision != revision or not self._repository.delete(kind, record_id, revision):
            raise HistoryChangedError("Deletion impact changed; preview it again.")

    def retention_days(self) -> int:
        return self._repository.retention_days()

    def set_retention_days(self, days: int) -> int:
        if not 7 <= days <= 3650:
            raise ValueError("Retention must be between 7 and 3650 days.")
        return self._repository.set_retention_days(days)

    def cleanup(self, trigger: str = "manual") -> CleanupResult:
        return self._repository.cleanup(trigger=trigger)

    def baseline(self) -> tuple[BaselineMetric, ...]:
        return self._repository.baseline()
