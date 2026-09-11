from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sysmind.application.ports.scans import ScanRepository
from sysmind.domain.diagnostics import ScanRecord, ScanStatus, StepStatus
from sysmind.infrastructure.database.models import ScanStepEvent, SystemScan


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _to_record(model: SystemScan) -> ScanRecord:
    summary = cast(
        dict[str, object] | None,
        json.loads(model.summary_json) if model.summary_json else None,
    )
    failures = tuple(cast(list[dict[str, str]], json.loads(model.failures_json)))
    return ScanRecord(
        id=model.id,
        status=cast(ScanStatus, model.status),
        progress=model.progress,
        current_step=model.current_step,
        started_at=model.started_at.isoformat(),
        finished_at=model.finished_at.isoformat() if model.finished_at else None,
        summary=summary,
        failures=failures,
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
    ) -> ScanRecord:
        with self._sessions.begin() as session:
            model = session.get(SystemScan, scan_id)
            if model is None:
                raise KeyError(scan_id)
            model.status = status
            model.progress = progress
            model.current_step = current_step
            model.finished_at = _parse_time(finished_at)
            if summary is not None:
                model.summary_json = json.dumps(summary, ensure_ascii=False)
            if failures is not None:
                model.failures_json = json.dumps(list(failures), ensure_ascii=False)
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
                failures = json.loads(model.failures_json)
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
