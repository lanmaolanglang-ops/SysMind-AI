from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from sysmind.application.ports.actions import ActionRepository
from sysmind.domain.actions import (
    ActionCandidate,
    ActionRecord,
    ActionStatus,
    StartupActionCandidate,
    StartupSourceKind,
)
from sysmind.infrastructure.database.models import (
    ActionEventModel,
    ActionModel,
    ActionPlanModel,
    RecoveryRecordModel,
    UserConfirmationModel,
)


def _record(model: ActionModel) -> ActionRecord:
    return ActionRecord(
        model.id,
        model.plan_id,
        model.diagnosis_id,
        model.tool_name,
        model.tool_version,
        model.target_id,
        model.target_name,
        model.source_kind,
        model.observed_revision,
        cast(ActionStatus, model.status),
        model.recovery_id,
        model.error_code,
        model.error_message,
        model.created_at.isoformat(),
        model.updated_at.isoformat(),
    )


class SqlAlchemyActionRepository(ActionRepository):
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def create(
        self,
        *,
        plan_id: str,
        action_id: str,
        diagnosis_id: str,
        tool_name: str,
        target: ActionCandidate,
        created_at: str,
    ) -> ActionRecord:
        now = datetime.fromisoformat(created_at)
        with self._sessions.begin() as session:
            session.add(
                ActionPlanModel(
                    id=plan_id, diagnosis_id=diagnosis_id, status="proposed", created_at=now
                )
            )
            session.flush()
            model = ActionModel(
                id=action_id,
                plan_id=plan_id,
                diagnosis_id=diagnosis_id,
                tool_name=tool_name,
                tool_version="1.0",
                target_id=target.item_id,
                target_name=target.name,
                source_kind=target.source_kind,
                observed_revision=target.observed_revision,
                status="proposed",
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            session.flush()
            session.add(
                ActionEventModel(
                    action_id=action_id, event_type="proposed", data_json="{}", created_at=now
                )
            )
        return _record(model)

    def create_restore(
        self, *, plan_id: str, action_id: str, original: ActionRecord, created_at: str
    ) -> ActionRecord:
        if not original.recovery_id:
            raise ValueError("Action has no recovery record.")
        target = StartupActionCandidate(
            original.recovery_id,
            original.target_name,
            cast(StartupSourceKind, original.source_kind),
            None,
            original.observed_revision,
        )
        return self.create(
            plan_id=plan_id,
            action_id=action_id,
            diagnosis_id=original.diagnosis_id,
            tool_name="startup.restore_current_user",
            target=target,
            created_at=created_at,
        )

    def get(self, action_id: str) -> ActionRecord | None:
        with self._sessions() as session:
            model = session.get(ActionModel, action_id)
            return _record(model) if model else None

    def recent(self, limit: int = 20) -> list[ActionRecord]:
        with self._sessions() as session:
            return [
                _record(item)
                for item in session.scalars(
                    select(ActionModel).order_by(ActionModel.created_at.desc()).limit(limit)
                )
            ]

    def set_status(
        self,
        action_id: str,
        *,
        status: str,
        updated_at: str,
        recovery_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> ActionRecord:
        now = datetime.fromisoformat(updated_at)
        with self._sessions.begin() as session:
            model = session.get(ActionModel, action_id)
            if model is None:
                raise KeyError(action_id)
            model.status, model.updated_at = status, now
            model.error_code, model.error_message = error_code, error_message
            plan = session.get(ActionPlanModel, model.plan_id)
            if plan is not None:
                plan.status = status
            if recovery_id is not None:
                model.recovery_id = recovery_id
                session.add(
                    RecoveryRecordModel(
                        id=recovery_id, action_id=action_id, status="available", created_at=now
                    )
                )
            session.add(
                ActionEventModel(
                    action_id=action_id, event_type=status, data_json="{}", created_at=now
                )
            )
        return _record(model)

    def add_confirmation(
        self, action_id: str, *, ticket_digest: str, expires_at: str, created_at: str
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                UserConfirmationModel(
                    action_id=action_id,
                    ticket_digest=ticket_digest,
                    decision="confirmed",
                    expires_at=datetime.fromisoformat(expires_at),
                    created_at=datetime.fromisoformat(created_at),
                )
            )

    def add_rejection(self, action_id: str, *, created_at: str) -> None:
        now = datetime.fromisoformat(created_at)
        digest = hashlib.sha256(f"rejected:{action_id}:{created_at}".encode()).hexdigest()
        with self._sessions.begin() as session:
            session.add(
                UserConfirmationModel(
                    action_id=action_id,
                    ticket_digest=digest,
                    decision="rejected",
                    expires_at=now,
                    consumed_at=now,
                    created_at=now,
                )
            )

    def add_confirmation_stage(self, action_id: str, *, stage: int, created_at: str) -> None:
        now = datetime.fromisoformat(created_at)
        digest = hashlib.sha256(
            f"confirmed_stage_{stage}:{action_id}:{created_at}".encode()
        ).hexdigest()
        with self._sessions.begin() as session:
            session.add(
                UserConfirmationModel(
                    action_id=action_id,
                    ticket_digest=digest,
                    decision=f"confirmed_stage_{stage}",
                    expires_at=now,
                    consumed_at=now,
                    created_at=now,
                )
            )

    def consume_confirmation(self, action_id: str, *, ticket_digest: str, consumed_at: str) -> bool:
        now = datetime.fromisoformat(consumed_at)
        with self._sessions.begin() as session:
            row = session.scalar(
                select(UserConfirmationModel).where(
                    UserConfirmationModel.action_id == action_id,
                    UserConfirmationModel.ticket_digest == ticket_digest,
                )
            )
            expires_at = row.expires_at if row is not None else None
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if row is None or row.consumed_at is not None or expires_at is None or expires_at < now:
                return False
            row.consumed_at = now
            return True

    def consume_recovery(self, recovery_id: str, *, consumed_at: str) -> None:
        now = datetime.fromisoformat(consumed_at)
        with self._sessions.begin() as session:
            recovery = session.get(RecoveryRecordModel, recovery_id)
            if recovery is None:
                raise KeyError(recovery_id)
            recovery.status, recovery.consumed_at = "consumed", now
            original = session.get(ActionModel, recovery.action_id)
            if original is not None:
                original.recovery_id = None

    def mark_interrupted(self, updated_at: str) -> int:
        now = datetime.fromisoformat(updated_at)
        with self._sessions.begin() as session:
            rows = list(
                session.scalars(
                    select(ActionModel).where(
                        ActionModel.status.in_(
                            (
                                "awaiting_second_confirmation",
                                "confirmed",
                                "executing",
                                "verifying",
                            )
                        )
                    )
                )
            )
            for row in rows:
                row.status, row.updated_at = "interrupted", now
                row.error_code = "backend_restarted"
                row.error_message = "本地服务重启，动作未自动重放。"
                plan = session.get(ActionPlanModel, row.plan_id)
                if plan is not None:
                    plan.status = "interrupted"
            return len(rows)

    def close(self) -> None:
        bind = self._sessions.kw.get("bind")
        if bind is not None:
            bind.dispose()
