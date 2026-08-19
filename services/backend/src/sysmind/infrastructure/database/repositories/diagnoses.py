from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sysmind.application.ports.diagnoses import DiagnosisRepository
from sysmind.domain.diagnosis import (
    DiagnosisCategory,
    DiagnosisRecord,
    DiagnosisReport,
    DiagnosisStatus,
    DiagnosisToolCall,
    EvidenceReference,
    Finding,
    Severity,
)
from sysmind.infrastructure.database.models import (
    Diagnosis,
    DiagnosisFeedback,
    DiagnosisModelCall,
    DiagnosisToolCallModel,
)


def _report(data: dict[str, object] | None) -> DiagnosisReport | None:
    if data is None:
        return None
    findings = tuple(
        Finding(
            id=cast(str, item["id"]),
            code=cast(str, item["code"]),
            severity=cast(Severity, item["severity"]),
            title=cast(str, item["title"]),
            explanation=cast(str, item["explanation"]),
            recommendation=cast(str, item["recommendation"]),
            confidence=float(cast(float, item["confidence"])),
            evidence=tuple(
                EvidenceReference(cast(str, ref["tool_call_id"]), cast(str, ref["field_path"]))
                for ref in cast(list[dict[str, object]], item["evidence"])
            ),
        )
        for item in cast(list[dict[str, object]], data["findings"])
    )
    return DiagnosisReport(
        cast(str, data["schema_version"]),
        cast(str, data["summary"]),
        cast(DiagnosisCategory, data["category"]),
        findings,
        float(cast(float, data["confidence"])),
        tuple(cast(list[str], data["limitations"])),
        cast(str, data["model_explanation"]),
    )


def _record(model: Diagnosis) -> DiagnosisRecord:
    report_data = (
        cast(dict[str, object], json.loads(model.report_json)) if model.report_json else None
    )
    return DiagnosisRecord(
        model.id,
        cast(DiagnosisStatus, model.status),
        model.user_question,
        cast(DiagnosisCategory, model.category),
        model.provider,
        tuple(cast(list[dict[str, object]], json.loads(model.plan_json))),
        model.progress,
        model.current_step,
        _report(report_data),
        model.report_markdown,
        model.failure_code,
        model.failure_message,
        model.created_at.isoformat(),
        model.completed_at.isoformat() if model.completed_at else None,
        model.schema_version,
    )


class SqlAlchemyDiagnosisRepository(DiagnosisRepository):
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def create(
        self,
        *,
        diagnosis_id: str,
        question: str,
        category: DiagnosisCategory,
        provider: str,
        plan: tuple[dict[str, object], ...],
        created_at: str,
    ) -> DiagnosisRecord:
        with self._sessions.begin() as session:
            model = Diagnosis(
                id=diagnosis_id,
                status="queued",
                user_question=question,
                category=category,
                provider=provider,
                plan_json=json.dumps(plan, ensure_ascii=False),
                progress=0,
                created_at=datetime.fromisoformat(created_at),
                schema_version="1.0",
            )
            session.add(model)
        return _record(model)

    def get(self, diagnosis_id: str) -> DiagnosisRecord | None:
        with self._sessions() as session:
            model = session.get(Diagnosis, diagnosis_id)
            return _record(model) if model else None

    def recent(self, limit: int = 20) -> list[DiagnosisRecord]:
        with self._sessions() as session:
            statement = select(Diagnosis).order_by(Diagnosis.created_at.desc()).limit(limit)
            return [_record(model) for model in session.scalars(statement)]

    def update_progress(
        self, diagnosis_id: str, *, status: str, progress: int, current_step: str | None
    ) -> None:
        with self._sessions.begin() as session:
            model = session.get(Diagnosis, diagnosis_id)
            if model is None:
                raise KeyError(diagnosis_id)
            model.status, model.progress, model.current_step = status, progress, current_step

    def complete(
        self,
        diagnosis_id: str,
        *,
        status: str,
        report: DiagnosisReport,
        markdown: str,
        completed_at: str,
    ) -> DiagnosisRecord:
        with self._sessions.begin() as session:
            model = session.get(Diagnosis, diagnosis_id)
            if model is None:
                raise KeyError(diagnosis_id)
            model.status, model.progress, model.current_step = status, 100, None
            model.report_json = json.dumps(asdict(report), ensure_ascii=False)
            model.report_markdown = markdown
            model.completed_at = datetime.fromisoformat(completed_at)
        return _record(model)

    def fail(
        self, diagnosis_id: str, *, status: str, code: str, message: str, completed_at: str
    ) -> DiagnosisRecord:
        with self._sessions.begin() as session:
            model = session.get(Diagnosis, diagnosis_id)
            if model is None:
                raise KeyError(diagnosis_id)
            model.status, model.failure_code, model.failure_message = status, code, message
            model.current_step = None
            model.completed_at = datetime.fromisoformat(completed_at)
        return _record(model)

    def create_tool_call(
        self,
        *,
        call_id: str,
        diagnosis_id: str,
        tool_name: str,
        tool_version: str,
        arguments: dict[str, object],
        arguments_hash: str,
        started_at: str,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                DiagnosisToolCallModel(
                    id=call_id,
                    diagnosis_id=diagnosis_id,
                    tool_name=tool_name,
                    tool_version=tool_version,
                    arguments_json=json.dumps(arguments, ensure_ascii=False),
                    arguments_hash=arguments_hash,
                    status="running",
                    started_at=datetime.fromisoformat(started_at),
                )
            )

    def finish_tool_call(
        self,
        call_id: str,
        *,
        status: str,
        result: object | None,
        summary: dict[str, object] | None,
        error_code: str | None,
        error_message: str | None,
        duration_ms: int,
        finished_at: str,
    ) -> None:
        with self._sessions.begin() as session:
            model = session.get(DiagnosisToolCallModel, call_id)
            if model is None:
                raise KeyError(call_id)
            model.status, model.error_code, model.error_message = status, error_code, error_message
            model.result_json = (
                json.dumps(result, ensure_ascii=False) if result is not None else None
            )
            model.summary_json = (
                json.dumps(summary, ensure_ascii=False) if summary is not None else None
            )
            model.duration_ms, model.finished_at = duration_ms, datetime.fromisoformat(finished_at)

    def tool_calls(self, diagnosis_id: str) -> tuple[DiagnosisToolCall, ...]:
        with self._sessions() as session:
            statement = (
                select(DiagnosisToolCallModel)
                .where(DiagnosisToolCallModel.diagnosis_id == diagnosis_id)
                .order_by(DiagnosisToolCallModel.started_at)
            )
            return tuple(
                DiagnosisToolCall(
                    item.id,
                    item.diagnosis_id,
                    item.tool_name,
                    item.tool_version,
                    item.status,
                    json.loads(item.result_json) if item.result_json else None,
                    cast(dict[str, object], json.loads(item.summary_json))
                    if item.summary_json
                    else None,
                    item.error_code,
                )
                for item in session.scalars(statement)
            )

    def add_feedback(
        self, diagnosis_id: str, helpful: bool, comment: str | None, created_at: str
    ) -> None:
        with self._sessions.begin() as session:
            if session.get(Diagnosis, diagnosis_id) is None:
                raise KeyError(diagnosis_id)
            session.add(
                DiagnosisFeedback(
                    diagnosis_id=diagnosis_id,
                    helpful=helpful,
                    comment=comment,
                    created_at=datetime.fromisoformat(created_at),
                )
            )

    def mark_interrupted(self, completed_at: str) -> int:
        with self._sessions.begin() as session:
            models = list(
                session.scalars(
                    select(Diagnosis).where(Diagnosis.status.in_(("queued", "running")))
                )
            )
            for model in models:
                model.status, model.failure_code = "interrupted", "backend_restarted"
                model.failure_message = "本地服务重启，诊断未自动重放。"
                model.completed_at = datetime.fromisoformat(completed_at)
            return len(models)

    def add_model_call(
        self,
        diagnosis_id: str,
        *,
        provider: str,
        status: str,
        request_hash: str,
        response_hash: str | None,
        duration_ms: int,
        error_code: str | None,
        created_at: str,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                DiagnosisModelCall(
                    diagnosis_id=diagnosis_id,
                    provider=provider,
                    status=status,
                    request_hash=request_hash,
                    response_hash=response_hash,
                    duration_ms=duration_ms,
                    error_code=error_code,
                    created_at=datetime.fromisoformat(created_at),
                )
            )
