from __future__ import annotations

import logging

from sysmind.application.ports.history import HistoryRepository
from sysmind.domain.history import (
    BaselineMetric,
    CleanupResult,
    CleanupTrigger,
    DeletionImpact,
    HistoryKind,
)
from sysmind.observability.logging import log_event

_LOGGER = logging.getLogger(__name__)


class HistoryChangedError(RuntimeError):
    pass


class HistoryProtectedError(RuntimeError):
    pass


class HistoryService:
    def __init__(self, repository: HistoryRepository) -> None:
        self._repository = repository

    def impact(self, kind: HistoryKind, record_id: str) -> DeletionImpact | None:
        """Preview deletion impact for one record.

        Returns ``None`` when the record does not exist (callers map that to 404).
        The destructive :meth:`delete` raises ``LookupError`` for the same missing
        record so a delete cannot silently no-op; the asymmetry is intentional.
        """
        return self._repository.impact(kind, record_id)

    def delete(self, kind: HistoryKind, record_id: str, revision: str) -> None:
        """Delete one record after a matching impact preview.

        Raises ``LookupError`` when the record is missing (same condition as
        :meth:`impact` returning ``None``).
        """
        impact = self._repository.impact(kind, record_id)
        if impact is None:
            raise LookupError(f"History record not found: {record_id}")
        if not impact.deletable:
            raise HistoryProtectedError(impact.protected_reason or "Record is protected.")
        # The repository re-checks deletable + revision inside the delete transaction,
        # so a concurrent protection change cannot slip through this gap.
        if impact.revision != revision or not self._repository.delete(kind, record_id, revision):
            raise HistoryChangedError("Deletion impact changed; preview it again.")
        log_event(
            _LOGGER,
            logging.WARNING,
            "History record deleted.",
            component="history",
            event_type="history_record_deleted",
            kind=kind,
            record_id=record_id,
        )

    def retention_days(self) -> int:
        return self._repository.retention_days()

    def set_retention_days(self, days: int) -> int:
        if not 7 <= days <= 3650:
            raise ValueError("Retention must be between 7 and 3650 days.")
        return self._repository.set_retention_days(days)

    def cleanup(self, trigger: CleanupTrigger = "manual") -> CleanupResult:
        result = self._repository.cleanup(trigger=trigger)
        log_event(
            _LOGGER,
            logging.WARNING,
            "History retention cleanup completed.",
            component="history",
            event_type="history_cleanup_completed",
            trigger=trigger,
            deleted_scans=result.deleted_scans,
            deleted_diagnoses=result.deleted_diagnoses,
            deleted_log_analyses=result.deleted_log_analyses,
            protected_records=result.protected_records,
        )
        return result

    def baseline(self) -> tuple[BaselineMetric, ...]:
        return self._repository.baseline()
