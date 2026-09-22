from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from sysmind.application.ports.diagnoses import DiagnosisRepository
from sysmind.domain.diagnosis import (
    DiagnosisCategory,
    DiagnosisHypothesis,
    DiagnosisRecord,
    DiagnosisReport,
    DiagnosisStatus,
    DiagnosisToolCall,
    EvidenceReference,
    Finding,
    HypothesisStatus,
    Severity,
    StopReason,
)
from sysmind.infrastructure.database.models import (
    AgentDecisionModel,
    AgentPlanModel,
    AgentStopReasonModel,
    Diagnosis,
    DiagnosisFeedback,
    DiagnosisHypothesisModel,
    DiagnosisModelCall,
    DiagnosisStepModel,
    DiagnosisToolCallModel,
    TaskUserInputModel,
)
from sysmind.tools.executor import arguments_hash

# Registry names are validated as ``name@major.minor``; when a planner step omits the
# version suffix we fall back to the baseline version instead of failing the whole plan.
DEFAULT_TOOL_VERSION = "1.0"

_TERMINAL_STATUSES = frozenset(
    {"completed", "partial", "cancelled", "failed", "interrupted"}
)
# A step that already reached one of these states must not be rewritten by a late finish.
_TERMINAL_STEP_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "timed_out", "skipped_duplicate"}
)


def _loads(value: str | None, default: object) -> object:
    """Parse stored JSON; a corrupt row must not break the read path."""
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _split_tool_reference(reference: str) -> tuple[str, str]:
    parts = reference.rsplit("@", 1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return reference, DEFAULT_TOOL_VERSION


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
        for item in cast(list[dict[str, object]], data.get("findings", []))
    )
    hypotheses = tuple(
        DiagnosisHypothesis(
            id=cast(str, item["id"]),
            key=cast(str, item["key"]),
            hypothesis=cast(str, item["hypothesis"]),
            rationale=cast(str, item["rationale"]),
            supporting_evidence=tuple(
                EvidenceReference(cast(str, ref["tool_call_id"]), cast(str, ref["field_path"]))
                for ref in cast(list[dict[str, object]], item["supporting_evidence"])
            ),
            contradicting_evidence=tuple(
                EvidenceReference(cast(str, ref["tool_call_id"]), cast(str, ref["field_path"]))
                for ref in cast(list[dict[str, object]], item["contradicting_evidence"])
            ),
            confidence=float(cast(float, item["confidence"])),
            status=cast(HypothesisStatus, item["status"]),
        )
        for item in cast(list[dict[str, object]], data.get("hypotheses", []))
    )
    return DiagnosisReport(
        cast(str, data.get("schema_version", "1.0")),
        cast(str, data.get("summary", "")),
        cast(DiagnosisCategory, data.get("category", "performance")),
        findings,
        float(cast(float, data.get("confidence", 0.0))),
        tuple(cast(list[str], data.get("limitations", []))),
        cast(str, data.get("model_explanation", "")),
        hypotheses,
    )


def _record(model: Diagnosis) -> DiagnosisRecord:
    report_data = cast(dict[str, object] | None, _loads(model.report_json, None))
    return DiagnosisRecord(
        model.id,
        cast(DiagnosisStatus, model.status),
        model.user_question,
        cast(DiagnosisCategory, model.category),
        model.provider,
        tuple(cast(list[dict[str, object]], _loads(model.plan_json, []))),
        model.progress,
        model.current_step,
        _report(report_data),
        model.report_markdown,
        model.failure_code,
        model.failure_message,
        model.created_at.isoformat(),
        model.completed_at.isoformat() if model.completed_at else None,
        model.schema_version,
        model.plan_confidence,
        model.planner_status,
        model.clarification_question,
        model.agent_round_count,
        model.max_agent_rounds,
        model.max_tool_calls,
        cast(StopReason | None, model.stop_reason),
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
            # CAS: a late progress write must not revive a terminal diagnosis
            # (e.g. overwrite cancelled/failed after the run already stopped).
            if model.status in _TERMINAL_STATUSES and status not in _TERMINAL_STATUSES:
                return
            model.status, model.progress, model.current_step = status, progress, current_step

    def save_agent_plan(
        self,
        diagnosis_id: str,
        *,
        provider: str,
        plan: dict[str, object],
        revision: int,
        created_at: str,
    ) -> tuple[str, tuple[str, ...]]:
        plan_id = str(uuid.uuid4())
        steps = cast(list[dict[str, object]], plan.get("steps", []))
        step_ids: list[str] = []
        with self._sessions.begin() as session:
            diagnosis = session.get(Diagnosis, diagnosis_id)
            if diagnosis is None:
                raise KeyError(diagnosis_id)
            diagnosis.category = str(plan["problem_category"])
            diagnosis.plan_confidence = float(cast(float, plan["confidence"]))
            diagnosis.planner_status = str(plan["status"])
            diagnosis.clarification_question = cast(str | None, plan["clarification_question"])
            # NOTE: agent_round_count tracks the planner/agent revision number (the value
            # the coordinator reads back as `revision`), not raw model rounds.
            diagnosis.agent_round_count = max(diagnosis.agent_round_count, revision)
            current_plan = [
                {
                    "tool": step["tool"],
                    "arguments": step.get("arguments", {}),
                    "purpose": step["reason"],
                    "reason": step["reason"],
                }
                for step in steps
            ]
            # `diagnoses.plan_json` is the current UI projection. Historical revisions
            # remain in `agent_plans`; appending here mixed old and new plans and made
            # the desktop render stale duplicate steps.
            diagnosis.plan_json = json.dumps(current_plan, ensure_ascii=False)
            session.add(
                AgentPlanModel(
                    id=plan_id,
                    diagnosis_id=diagnosis_id,
                    revision=revision,
                    provider=provider,
                    problem_category=str(plan["problem_category"]),
                    confidence=float(cast(float, plan["confidence"])),
                    status=str(plan["status"]),
                    plan_json=json.dumps(plan, ensure_ascii=False),
                    created_at=datetime.fromisoformat(created_at),
                )
            )
            for index, step in enumerate(steps):
                step_id = str(uuid.uuid4())
                step_ids.append(step_id)
                tool, version = _split_tool_reference(str(step["tool"]))
                arguments = cast(dict[str, object], step.get("arguments", {}))
                session.add(
                    DiagnosisStepModel(
                        id=step_id,
                        plan_id=plan_id,
                        diagnosis_id=diagnosis_id,
                        sequence=index,
                        tool_name=tool,
                        tool_version=version,
                        reason=str(step["reason"]),
                        arguments_hash=arguments_hash(arguments),
                        status="planned",
                        created_at=datetime.fromisoformat(created_at),
                    )
                )
        return plan_id, tuple(step_ids)

    def finish_diagnosis_step(self, step_id: str, *, status: str, tool_call_id: str | None) -> None:
        with self._sessions.begin() as session:
            model = session.get(DiagnosisStepModel, step_id)
            if model is None:
                raise KeyError(step_id)
            # CAS: do not rewrite a step that already finished (e.g. skipped_duplicate).
            if model.status in _TERMINAL_STEP_STATUSES:
                return
            model.status = status
            model.tool_call_id = tool_call_id

    def add_agent_decision(
        self,
        diagnosis_id: str,
        *,
        plan_id: str | None,
        decision_type: str,
        reason: str,
        data: dict[str, object],
        created_at: str,
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                AgentDecisionModel(
                    diagnosis_id=diagnosis_id,
                    plan_id=plan_id,
                    decision_type=decision_type,
                    reason=reason,
                    data_json=json.dumps(data, ensure_ascii=False),
                    created_at=datetime.fromisoformat(created_at),
                )
            )

    def wait_for_input(self, diagnosis_id: str, *, question: str) -> DiagnosisRecord:
        with self._sessions.begin() as session:
            model = session.get(Diagnosis, diagnosis_id)
            if model is None:
                raise KeyError(diagnosis_id)
            model.status = "waiting_user_input"
            # The pending question belongs in clarification_question; current_step keeps
            # its own "what is happening now" meaning and must not be repurposed.
            model.clarification_question = question
        return _record(model)

    def resume_with_input(
        self, diagnosis_id: str, *, input_text: str, created_at: str
    ) -> DiagnosisRecord | None:
        with self._sessions.begin() as session:
            claimed_id = session.scalar(
                update(Diagnosis)
                .where(
                    Diagnosis.id == diagnosis_id,
                    Diagnosis.status == "waiting_user_input",
                )
                .values(
                    status="running",
                    current_step="正在根据补充信息调整检查项目",
                    clarification_question=None,
                    failure_code=None,
                    failure_message=None,
                    completed_at=None,
                )
                .returning(Diagnosis.id)
            )
            if claimed_id is None:
                return None
            sequence = (
                session.scalar(
                    select(func.count(TaskUserInputModel.id)).where(
                        TaskUserInputModel.diagnosis_id == diagnosis_id
                    )
                )
                or 0
            )
            session.add(
                TaskUserInputModel(
                    diagnosis_id=diagnosis_id,
                    sequence=sequence + 1,
                    input_text=input_text,
                    created_at=datetime.fromisoformat(created_at),
                )
            )
            model = session.get(Diagnosis, diagnosis_id)
            if model is None:
                raise KeyError(diagnosis_id)
        return _record(model)

    def user_inputs(self, diagnosis_id: str) -> tuple[str, ...]:
        with self._sessions() as session:
            statement = (
                select(TaskUserInputModel.input_text)
                .where(TaskUserInputModel.diagnosis_id == diagnosis_id)
                .order_by(TaskUserInputModel.sequence)
            )
            return tuple(session.scalars(statement))

    def replace_hypotheses(
        self,
        diagnosis_id: str,
        *,
        hypotheses: tuple[DiagnosisHypothesis, ...],
        updated_at: str,
    ) -> None:
        timestamp = datetime.fromisoformat(updated_at)
        with self._sessions.begin() as session:
            diagnosis = session.get(Diagnosis, diagnosis_id)
            # CAS: do not rewrite hypothesis state for a diagnosis that already finished.
            if diagnosis is None or diagnosis.status in _TERMINAL_STATUSES:
                return
            existing = {
                item.hypothesis_key: item
                for item in session.scalars(
                    select(DiagnosisHypothesisModel).where(
                        DiagnosisHypothesisModel.diagnosis_id == diagnosis_id
                    )
                )
            }
            active_keys: set[str] = set()
            for hypothesis in hypotheses:
                active_keys.add(hypothesis.key)
                model = existing.get(hypothesis.key)
                if model is None:
                    model = DiagnosisHypothesisModel(
                        id=hypothesis.id,
                        diagnosis_id=diagnosis_id,
                        hypothesis_key=hypothesis.key,
                        created_at=timestamp,
                    )
                    session.add(model)
                model.hypothesis = hypothesis.hypothesis
                model.rationale = hypothesis.rationale
                model.supporting_evidence_json = json.dumps(
                    [asdict(item) for item in hypothesis.supporting_evidence], ensure_ascii=False
                )
                model.contradicting_evidence_json = json.dumps(
                    [asdict(item) for item in hypothesis.contradicting_evidence],
                    ensure_ascii=False,
                )
                model.confidence = hypothesis.confidence
                model.status = hypothesis.status
                model.updated_at = timestamp
            obsolete = delete(DiagnosisHypothesisModel).where(
                DiagnosisHypothesisModel.diagnosis_id == diagnosis_id
            )
            if active_keys:
                obsolete = obsolete.where(
                    DiagnosisHypothesisModel.hypothesis_key.not_in(active_keys)
                )
            session.execute(obsolete)

    def record_stop_reason(
        self,
        diagnosis_id: str,
        *,
        reason: StopReason,
        detail: str,
        terminal_status: str,
        created_at: str,
    ) -> None:
        with self._sessions.begin() as session:
            diagnosis = session.get(Diagnosis, diagnosis_id)
            if diagnosis is None:
                raise KeyError(diagnosis_id)
            diagnosis.stop_reason = reason
            session.add(
                AgentStopReasonModel(
                    diagnosis_id=diagnosis_id,
                    reason=reason,
                    detail=detail,
                    terminal_status=terminal_status,
                    created_at=datetime.fromisoformat(created_at),
                )
            )

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
        redacted_arguments: dict[str, object],
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
                    arguments_json=json.dumps(redacted_arguments, ensure_ascii=False),
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
                    _loads(item.result_json, None),
                    cast(dict[str, object] | None, _loads(item.summary_json, None)),
                    item.error_code,
                    item.started_at.isoformat(),
                    item.finished_at.isoformat() if item.finished_at else None,
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
            # NOTE: `waiting_user_input` is intentionally NOT interrupted. A diagnosis
            # paused for clarification stays resumable after a restart (the user's answer
            # is submitted later); forcing it to `interrupted` would strand their input.
            for model in models:
                model.status, model.failure_code = "interrupted", "backend_restarted"
                model.failure_message = "本地服务重启，诊断未自动重放。"
                model.completed_at = datetime.fromisoformat(completed_at)
                model.stop_reason = "backend_restarted"
                session.add(
                    AgentStopReasonModel(
                        diagnosis_id=model.id,
                        reason="backend_restarted",
                        detail="本地服务重启，中断中的工具调用不会自动重放。",
                        terminal_status="interrupted",
                        created_at=datetime.fromisoformat(completed_at),
                    )
                )
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
