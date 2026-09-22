from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from sysmind.application.ports.scans import ScanRepository
from sysmind.application.ports.state_conflict import StateConflict
from sysmind.domain.diagnostics import ScanRecord, ScanStatus, StepStatus
from sysmind.infrastructure.database.cas import allowed_source_statuses
from sysmind.infrastructure.database.models import ScanStepEvent, SystemScan

_TERMINAL_STATUSES = frozenset({"completed", "partial", "cancelled", "failed"})
_NON_TERMINAL_STATUSES = frozenset({"queued", "running"})


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _loads(raw: str | None, default: object) -> object:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _to_record(model: SystemScan) -> ScanRecord:
    summary = cast(dict[str, object] | None, _loads(model.summary_json, None))
    failures = cast(list[dict[str, str]], _loads(model.failures_json, []))
    return ScanRecord(
        id=model.id,
        status=cast(ScanStatus, model.status),
        progress=model.progress,
        current_step=model.current_step,
        started_at=model.started_at.isoformat(),
        finished_at=model.finished_at.isoformat() if model.finished_at else None,
        summary=summary,
        failures=tuple(failures),
        schema_version=model.schema_version,
    )


class SqlAlchemyScanRepository(ScanRepository):
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def create(self, scan_id: str, started_at: str, schema_version: str) -> ScanRecord:
        with self._sessions.begin() as session:
            model = SystemScan(
                id=scan_id,
                scan_type="quick",
                status="queued",
                progress=0,
                started_at=datetime.fromisoformat(started_at),
                failures_json="[]",
                schema_version=schema_version,
            )
            session.add(model)
        return _to_record(model)

    def update(
        self,
        scan_id: str,
        *,
        status: ScanStatus,
        progress: int,
        current_step: str | None,
        finished_at: str | None = None,
        summary: dict[str, object] | None = None,
        failures: Sequence[dict[str, str]] | None = None,
        expected_statuses: Sequence[ScanStatus] | None = None,
    ) -> ScanRecord:
        allowed = allowed_source_statuses(
            target_status=status,
            non_terminal=_NON_TERMINAL_STATUSES,
            terminal=_TERMINAL_STATUSES,
            expected=expected_statuses,
        )
        values: dict[str, object] = {
            "status": status,
            "progress": progress,
            "current_step": current_step,
            "finished_at": _parse_time(finished_at),
        }
        if summary is not None:
            values["summary_json"] = json.dumps(summary, ensure_ascii=False)
        if failures is not None:
            values["failures_json"] = json.dumps(list(failures), ensure_ascii=False)
        with self._sessions.begin() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(SystemScan)
                    .where(SystemScan.id == scan_id, SystemScan.status.in_(allowed))
                    .values(**values)
                ),
            )
            model = session.get(SystemScan, scan_id)
            if model is None:
                raise KeyError(scan_id)
            if result.rowcount != 1 and (
                expected_statuses is not None
                or (status in _TERMINAL_STATUSES and model.status != status)
            ):
                # Progress writes that lose to a terminalizer are a silent no-op
                # (they must not revive the row). Explicit CAS and competing
                # terminal writes surface a conflict so exactly one winner sticks.
                raise StateConflict(
                    scan_id,
                    expected=allowed,
                    actual=model.status,
                )
            return _to_record(model)

    def add_step_event(
        self,
        *,
        scan_id: str,
        tool_name: str,
        tool_version: str,
        arguments_hash: str,
        status: StepStatus,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        result_summary: dict[str, object] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                ScanStepEvent(
                    scan_id=scan_id,
                    tool_name=tool_name,
                    tool_version=tool_version,
                    arguments_hash=arguments_hash,
                    status=status,
                    started_at=datetime.fromisoformat(started_at),
                    finished_at=datetime.fromisoformat(finished_at),
                    duration_ms=duration_ms,
                    result_summary_json=(
                        json.dumps(result_summary, ensure_ascii=False)
                        if result_summary is not None
                        else None
                    ),
                    error_code=error_code,
                    error_message=error_message,
                )
            )

    def get(self, scan_id: str) -> ScanRecord | None:
        with self._sessions() as session:
            model = session.get(SystemScan, scan_id)
            return _to_record(model) if model else None

    def recent(self, limit: int = 20) -> list[ScanRecord]:
        with self._sessions() as session:
            statement = select(SystemScan).order_by(SystemScan.started_at.desc()).limit(limit)
            return [_to_record(model) for model in session.scalars(statement)]

    def mark_interrupted(self, finished_at: str) -> int:
        with self._sessions.begin() as session:
            statement = select(SystemScan).where(SystemScan.status.in_(("queued", "running")))
            models = list(session.scalars(statement))
            for model in models:
                failures = cast(list[dict[str, str]], _loads(model.failures_json, []))
                failures.append(
                    {
                        "tool": model.current_step or "scan",
                        "code": "backend_restarted",
                        "message": "本地服务重启，之前的扫描已中止。",
                    }
                )
                model.status = "failed"
                model.current_step = None
                model.finished_at = datetime.fromisoformat(finished_at)
                model.failures_json = json.dumps(failures, ensure_ascii=False)
            return len(models)
