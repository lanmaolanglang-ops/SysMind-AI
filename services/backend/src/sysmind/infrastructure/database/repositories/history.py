from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import cast

from sqlalchemy import delete, func, select, union_all
from sqlalchemy.orm import Session, sessionmaker

from sysmind.domain.history import (
    BaselineMetric,
    CleanupResult,
    DeletionImpact,
    HistoryKind,
)
from sysmind.infrastructure.database.models import (
    ActionPlanModel,
    AgentDecisionModel,
    AgentPlanModel,
    AgentStopReasonModel,
    DataCleanupRunModel,
    DataRetentionPolicyModel,
    Diagnosis,
    DiagnosisFeedback,
    DiagnosisHypothesisModel,
    DiagnosisModelCall,
    DiagnosisStepModel,
    DiagnosisToolCallModel,
    EventLogAnalysis,
    EventLogStepEvent,
    ScanStepEvent,
    SystemScan,
    TaskUserInputModel,
)


class SqlAlchemyHistoryRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _impact(session: Session, kind: HistoryKind, record_id: str) -> DeletionImpact | None:
        model_type = {"scan": SystemScan, "diagnosis": Diagnosis, "log": EventLogAnalysis}[kind]
        model = session.get(model_type, record_id)
        if model is None:
            return None
        if kind == "scan":
            scan = cast(SystemScan, model)
            dependent = (
                session.scalar(
                    select(func.count())
                    .select_from(ScanStepEvent)
                    .where(ScanStepEvent.scan_id == record_id)
                )
                or 0
            )
            terminal = scan.finished_at is not None
            protected = None if terminal else "Active scans cannot be deleted."
            stamp, record_status = scan.finished_at, scan.status
        elif kind == "log":
            analysis = cast(EventLogAnalysis, model)
            dependent = (
                session.scalar(
                    select(func.count())
                    .select_from(EventLogStepEvent)
                    .where(EventLogStepEvent.analysis_id == record_id)
                )
                or 0
            )
            terminal = analysis.finished_at is not None
            protected = None if terminal else "Active log analyses cannot be deleted."
            stamp, record_status = analysis.finished_at, analysis.status
        else:
            diagnosis = cast(Diagnosis, model)
            # Every table that hangs off a diagnosis counts toward the reported impact so
            # the deletion preview and its revision token describe the whole cascade.
            # One UNION ALL query instead of a COUNT per child table (N+1).
            dependent = sum(
                row[0]
                for row in session.execute(
                    union_all(
                        *(
                            select(func.count())
                            .select_from(table)
                            .where(column == record_id)
                            for table, column in (
                                (DiagnosisToolCallModel, DiagnosisToolCallModel.diagnosis_id),
                                (DiagnosisFeedback, DiagnosisFeedback.diagnosis_id),
                                (DiagnosisModelCall, DiagnosisModelCall.diagnosis_id),
                                (AgentPlanModel, AgentPlanModel.diagnosis_id),
                                (DiagnosisStepModel, DiagnosisStepModel.diagnosis_id),
                                (AgentDecisionModel, AgentDecisionModel.diagnosis_id),
                                (
                                    DiagnosisHypothesisModel,
                                    DiagnosisHypothesisModel.diagnosis_id,
                                ),
                                (AgentStopReasonModel, AgentStopReasonModel.diagnosis_id),
                                (TaskUserInputModel, TaskUserInputModel.diagnosis_id),
                            )
                        )
                    )
                )
            )
            action_plans = (
                session.scalar(
                    select(func.count())
                    .select_from(ActionPlanModel)
                    .where(ActionPlanModel.diagnosis_id == record_id)
                )
                or 0
            )
            terminal = diagnosis.completed_at is not None
            protected = (
                "Diagnoses linked to controlled-action audit are retained."
                if action_plans
                else None
                if terminal
                else "Active diagnoses cannot be deleted."
            )
            stamp, record_status = diagnosis.completed_at, diagnosis.status
        revision_source = f"{kind}:{record_id}:{record_status}:{stamp}:{dependent}:{protected}"
        revision = hashlib.sha256(revision_source.encode()).hexdigest()
        return DeletionImpact(kind, record_id, revision, protected is None, dependent, protected)

    def impact(self, kind: HistoryKind, record_id: str) -> DeletionImpact | None:
        with self._sessions() as session:
            return self._impact(session, kind, record_id)

    def delete(self, kind: HistoryKind, record_id: str, revision: str) -> bool:
        with self._sessions.begin() as session:
            impact = self._impact(session, kind, record_id)
            if impact is None or not impact.deletable or impact.revision != revision:
                return False
            if kind == "scan":
                session.execute(delete(SystemScan).where(SystemScan.id == record_id))
            elif kind == "diagnosis":
                session.execute(delete(Diagnosis).where(Diagnosis.id == record_id))
            else:
                session.execute(delete(EventLogAnalysis).where(EventLogAnalysis.id == record_id))
            counts = {"scan": (1, 0, 0), "diagnosis": (0, 1, 0), "log": (0, 0, 1)}[kind]
            session.add(
                DataCleanupRunModel(
                    trigger="manual_delete",
                    target_kind=kind,
                    target_id=record_id,
                    deleted_scans=counts[0],
                    deleted_diagnoses=counts[1],
                    deleted_log_analyses=counts[2],
                    protected_records=0,
                    created_at=datetime.now(UTC),
                )
            )
            return True

    def retention_days(self) -> int:
        with self._sessions() as session:
            policy = session.get(DataRetentionPolicyModel, 1)
            return policy.retention_days if policy else 30

    def set_retention_days(self, days: int) -> int:
        with self._sessions.begin() as session:
            policy = session.get(DataRetentionPolicyModel, 1)
            if policy is None:
                session.add(
                    DataRetentionPolicyModel(
                        id=1, retention_days=days, updated_at=datetime.now(UTC)
                    )
                )
            else:
                policy.retention_days = days
                policy.updated_at = datetime.now(UTC)
        return days

    def cleanup(self, *, trigger: str) -> CleanupResult:
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=self.retention_days())
        with self._sessions.begin() as session:
            old_scans = list(
                session.scalars(select(SystemScan.id).where(SystemScan.finished_at < cutoff))
            )
            old_logs = list(
                session.scalars(
                    select(EventLogAnalysis.id).where(EventLogAnalysis.finished_at < cutoff)
                )
            )
            old_diagnoses = list(
                session.scalars(select(Diagnosis.id).where(Diagnosis.completed_at < cutoff))
            )
            protected_ids = (
                set(
                    session.scalars(
                        select(ActionPlanModel.diagnosis_id).where(
                            ActionPlanModel.diagnosis_id.in_(old_diagnoses)
                        )
                    )
                )
                if old_diagnoses
                else set()
            )
            deletable_diagnoses = [item for item in old_diagnoses if item not in protected_ids]
            if old_scans:
                session.execute(delete(SystemScan).where(SystemScan.id.in_(old_scans)))
            if old_logs:
                session.execute(delete(EventLogAnalysis).where(EventLogAnalysis.id.in_(old_logs)))
            if deletable_diagnoses:
                session.execute(delete(Diagnosis).where(Diagnosis.id.in_(deletable_diagnoses)))
            session.add(
                DataCleanupRunModel(
                    trigger=trigger,
                    cutoff_at=cutoff,
                    deleted_scans=len(old_scans),
                    deleted_diagnoses=len(deletable_diagnoses),
                    deleted_log_analyses=len(old_logs),
                    protected_records=len(protected_ids),
                    created_at=now,
                )
            )
        return CleanupResult(
            len(old_scans),
            len(deletable_diagnoses),
            len(old_logs),
            len(protected_ids),
            now.isoformat(),
        )

    def baseline(self) -> tuple[BaselineMetric, ...]:
        with self._sessions() as session:
            values = list(
                session.scalars(
                    select(SystemScan.summary_json)
                    .where(
                        SystemScan.finished_at.is_not(None), SystemScan.summary_json.is_not(None)
                    )
                    .order_by(SystemScan.started_at.desc())
                    .limit(10)
                )
            )
        samples: dict[str, list[float]] = {
            "cpu_percent": [],
            "memory_percent": [],
            "disk_peak_percent": [],
        }
        for raw in values:
            if raw is None:
                continue
            try:
                data = cast(dict[str, object], json.loads(raw))
                cpu_section = data.get("cpu")
                memory_section = data.get("memory")
                cpu = (
                    cast(dict[str, object], cpu_section).get("utilization_percent")
                    if isinstance(cpu_section, dict)
                    else None
                )
                memory = (
                    cast(dict[str, object], memory_section).get("utilization_percent")
                    if isinstance(memory_section, dict)
                    else None
                )
                raw_disks = data.get("disks")
                disks = (
                    cast(list[dict[str, object]], raw_disks)
                    if isinstance(raw_disks, list)
                    else []
                )
                disk_values = [
                    float(value)
                    for item in disks
                    if isinstance(item, dict)
                    and isinstance((value := item.get("utilization_percent")), (int, float))
                ]
                disk = max(disk_values, default=None)
                for name, value in (
                    ("cpu_percent", cpu),
                    ("memory_percent", memory),
                    ("disk_peak_percent", disk),
                ):
                    if isinstance(value, (int, float)):
                        samples[name].append(float(value))
            except (
                AttributeError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
                KeyError,
            ):
                # A malformed historical summary must never break the baseline view.
                continue
        return tuple(
            BaselineMetric(
                name,
                len(items),
                round(median(items), 1),
                round(items[0], 1),
                round(items[0] - median(items), 1),
            )
            for name, items in samples.items()
            if len(items) >= 2
        )
