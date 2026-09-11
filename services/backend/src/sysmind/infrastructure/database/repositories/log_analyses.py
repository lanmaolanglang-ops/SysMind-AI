from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sysmind.application.ports.log_analyses import LogAnalysisRepository
from sysmind.domain.diagnostics import StepStatus
from sysmind.domain.event_logs import AnalysisStatus, LogAnalysisRecord
from sysmind.infrastructure.database.models import EventLogAnalysis, EventLogStepEvent


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _to_record(model: EventLogAnalysis) -> LogAnalysisRecord:
    query = cast(dict[str, object], json.loads(model.query_json))
    summary = cast(
        dict[str, object] | None,
        json.loads(model.summary_json) if model.summary_json else None,
    )
    failures = tuple(cast(list[dict[str, str]], json.loads(model.failures_json)))
    return LogAnalysisRecord(
        id=model.id,
        status=cast(AnalysisStatus, model.status),
        progress=model.progress,
        current_step=model.current_step,
        started_at=model.started_at.isoformat(),
        finished_at=model.finished_at.isoformat() if model.finished_at else None,
        query=query,
        summary=summary,
        failures=failures,
        schema_version=model.schema_version,
    )


class SqlAlchemyLogAnalysisRepository(LogAnalysisRepository):
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def create(
        self, analysis_id: str, started_at: str, query: dict[str, object], schema_version: str
    ) -> LogAnalysisRecord:
        with self._sessions.begin() as session:
            model = EventLogAnalysis(
                id=analysis_id,
                status="queued",
                progress=0,
                started_at=datetime.fromisoformat(started_at),
                query_json=json.dumps(query, ensure_ascii=False),
                failures_json="[]",
                schema_version=schema_version,
            )
            session.add(model)
        return _to_record(model)

    def update(
        self,
        analysis_id: str,
        *,
        status: AnalysisStatus,
        progress: int,
        current_step: str | None,
        finished_at: str | None = None,
        summary: dict[str, object] | None = None,
        failures: Sequence[dict[str, str]] | None = None,
    ) -> LogAnalysisRecord:
        with self._sessions.begin() as session:
            model = session.get(EventLogAnalysis, analysis_id)
            if model is None:
                raise KeyError(analysis_id)
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
        analysis_id: str,
        tool_name: str,
        tool_version: str,
        status: StepStatus,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        arguments_hash: str,
        result_summary: dict[str, object] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                EventLogStepEvent(
                    analysis_id=analysis_id,
                    tool_name=tool_name,
                    tool_version=tool_version,
                    status=status,
                    started_at=datetime.fromisoformat(started_at),
                    finished_at=datetime.fromisoformat(finished_at),
                    duration_ms=duration_ms,
                    arguments_hash=arguments_hash,
                    result_summary_json=(
                        json.dumps(result_summary, ensure_ascii=False)
                        if result_summary is not None
                        else None
                    ),
                    error_code=error_code,
                    error_message=error_message,
                )
            )

    def get(self, analysis_id: str) -> LogAnalysisRecord | None:
        with self._sessions() as session:
            model = session.get(EventLogAnalysis, analysis_id)
            return _to_record(model) if model else None

    def recent(self, limit: int = 20) -> list[LogAnalysisRecord]:
        with self._sessions() as session:
            statement = (
                select(EventLogAnalysis).order_by(EventLogAnalysis.started_at.desc()).limit(limit)
            )
            return [_to_record(model) for model in session.scalars(statement)]

    def mark_interrupted(self, finished_at: str) -> int:
        with self._sessions.begin() as session:
            statement = select(EventLogAnalysis).where(
                EventLogAnalysis.status.in_(("queued", "running"))
            )
            models = list(session.scalars(statement))
            for model in models:
                failures = json.loads(model.failures_json)
                failures.append(
                    {
                        "tool": model.current_step or "log_analysis",
                        "code": "backend_restarted",
                        "message": "本地服务重启，之前的日志分析已中止。",
                    }
                )
                model.status = "failed"
                model.current_step = None
                model.finished_at = datetime.fromisoformat(finished_at)
                model.failures_json = json.dumps(failures, ensure_ascii=False)
            return len(models)
