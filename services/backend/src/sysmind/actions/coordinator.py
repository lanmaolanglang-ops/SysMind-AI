from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

from sysmind.application.ports.actions import (
    ActionRepository,
    ActionVerificationError,
    ProcessActionAdapter,
    StartupActionAdapter,
    TargetChangedError,
)
from sysmind.application.ports.diagnoses import DiagnosisRepository
from sysmind.domain.actions import ActionRecord, ProcessActionCandidate, StartupActionCandidate
from sysmind.security import ConsentError, ConsentService
from sysmind.tools.contracts import ToolPermissionError, ToolUnavailableError


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ActionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ActionCoordinator:
    def __init__(
        self,
        repository: ActionRepository,
        diagnoses: DiagnosisRepository,
        adapter: StartupActionAdapter,
        consent: ConsentService,
        process_adapter: ProcessActionAdapter | None = None,
    ) -> None:
        self._repository = repository
        self._diagnoses = diagnoses
        self._adapter = adapter
        self._consent = consent
        self._process_adapter = process_adapter
        self._lock = threading.Lock()

    def candidates(self, diagnosis_id: str) -> tuple[StartupActionCandidate, ...]:
        diagnosis = self._diagnoses.get(diagnosis_id)
        if diagnosis is None or diagnosis.status not in {"completed", "partial"}:
            raise ActionError("diagnosis_not_ready", "A completed diagnosis is required.")
        calls = self._diagnoses.tool_calls(diagnosis_id)
        if not any(
            call.status == "completed" and call.tool_name in {"startup.list", "startup.analyze"}
            for call in calls
        ):
            raise ActionError(
                "startup_evidence_required",
                "This diagnosis contains no completed startup evidence.",
            )
        return tuple(self._adapter.candidates())

    def create_disable(
        self, diagnosis_id: str, item_id: str, observed_revision: str
    ) -> ActionRecord:
        target = next(
            (item for item in self.candidates(diagnosis_id) if item.item_id == item_id), None
        )
        if target is None or target.observed_revision != observed_revision:
            raise ActionError("target_changed", "Startup target changed; refresh the plan.")
        return self._repository.create(
            plan_id=str(uuid.uuid4()),
            action_id=str(uuid.uuid4()),
            diagnosis_id=diagnosis_id,
            tool_name="startup.disable_current_user",
            target=target,
            created_at=_now(),
        )

    def process_candidates(self, diagnosis_id: str) -> tuple[ProcessActionCandidate, ...]:
        diagnosis = self._diagnoses.get(diagnosis_id)
        if diagnosis is None or diagnosis.status not in {"completed", "partial"}:
            raise ActionError("diagnosis_not_ready", "A completed diagnosis is required.")
        if self._process_adapter is None:
            raise ActionError("process_actions_unavailable", "Process actions are unavailable.")
        calls = tuple(
            call
            for call in self._diagnoses.tool_calls(diagnosis_id)
            if call.status == "completed" and call.tool_name == "process.high_usage"
        )
        referenced_call_ids = {
            evidence.tool_call_id
            for finding in (diagnosis.report.findings if diagnosis.report else ())
            for evidence in finding.evidence
        }
        evidence_pids = {
            int(item["pid"])
            for call in calls
            if call.id in referenced_call_ids and isinstance(call.result, list)
            for item in call.result
            if isinstance(item, dict) and isinstance(item.get("pid"), int)
        }
        if not evidence_pids:
            raise ActionError(
                "process_evidence_required",
                "This diagnosis contains no referenced high-usage process evidence.",
            )
        return tuple(
            item for item in self._process_adapter.candidates() if item.pid in evidence_pids
        )

    def create_process_close(
        self, diagnosis_id: str, item_id: str, observed_revision: str
    ) -> ActionRecord:
        target = next(
            (item for item in self.process_candidates(diagnosis_id) if item.item_id == item_id),
            None,
        )
        if target is None or target.observed_revision != observed_revision:
            raise ActionError("target_changed", "Process target changed; refresh the plan.")
        return self._repository.create(
            plan_id=str(uuid.uuid4()),
            action_id=str(uuid.uuid4()),
            diagnosis_id=diagnosis_id,
            tool_name="process.request_close_current_user",
            target=target,
            created_at=_now(),
        )

    def create_process_terminate(self, close_action_id: str) -> ActionRecord:
        original = self._required(close_action_id)
        if (
            original.tool_name != "process.request_close_current_user"
            or original.status != "close_pending"
        ):
            raise ActionError(
                "termination_not_allowed",
                "Forced termination requires a close request that remained pending.",
            )
        if self._process_adapter is None:
            raise ActionError("process_actions_unavailable", "Process actions are unavailable.")
        target = next(
            (
                item
                for item in self._process_adapter.candidates()
                if item.item_id == original.target_id
            ),
            None,
        )
        if target is None:
            raise ActionError("target_changed", "Process is no longer an eligible target.")
        return self._repository.create(
            plan_id=str(uuid.uuid4()),
            action_id=str(uuid.uuid4()),
            diagnosis_id=original.diagnosis_id,
            tool_name="process.terminate_current_user",
            target=target,
            created_at=_now(),
        )

    def create_restore(self, action_id: str) -> ActionRecord:
        original = self._required(action_id)
        if original.status not in {"succeeded", "verification_failed"} or not original.recovery_id:
            raise ActionError("recovery_unavailable", "This action has no available recovery.")
        if not self._adapter.recovery_exists(original.recovery_id):
            raise ActionError("recovery_unavailable", "Recovery material is unavailable.")
        return self._repository.create_restore(
            plan_id=str(uuid.uuid4()),
            action_id=str(uuid.uuid4()),
            original=original,
            created_at=_now(),
        )

    def confirm(self, action_id: str) -> tuple[ActionRecord, str | None, str | None]:
        action = self._required(action_id)
        if action.tool_name == "process.terminate_current_user" and action.status == "proposed":
            now = _now()
            self._repository.add_confirmation_stage(action.id, stage=1, created_at=now)
            action = self._repository.set_status(
                action.id, status="awaiting_second_confirmation", updated_at=now
            )
            return action, None, None
        if (
            action.tool_name == "process.terminate_current_user"
            and action.status == "awaiting_second_confirmation"
            and self._age_seconds(action) > 30
        ):
            self._repository.set_status(action.id, status="expired", updated_at=_now())
            raise ActionError("action_expired", "Termination confirmation window expired.")
        if action.status not in {"proposed", "awaiting_second_confirmation"}:
            raise ActionError("invalid_action_state", "Only a proposed action can be confirmed.")
        issued = self._consent.issue(
            action.id, action.tool_name, action.target_id, action.observed_revision
        )
        self._repository.add_confirmation(
            action.id, ticket_digest=issued.digest, expires_at=issued.expires_at, created_at=_now()
        )
        action = self._repository.set_status(action.id, status="confirmed", updated_at=_now())
        return action, issued.ticket, issued.expires_at

    def reject(self, action_id: str) -> ActionRecord:
        action = self._required(action_id)
        if action.status not in {"proposed", "awaiting_second_confirmation"}:
            raise ActionError("invalid_action_state", "Only a proposed action can be rejected.")
        now = _now()
        self._repository.add_rejection(action.id, created_at=now)
        return self._repository.set_status(action.id, status="rejected", updated_at=now)

    def execute(self, action_id: str, ticket: str) -> ActionRecord:
        with self._lock:
            action = self._required(action_id)
            if action.status != "confirmed":
                raise ActionError("invalid_action_state", "Action is not awaiting execution.")
            try:
                digest = self._consent.verify(
                    ticket, action.id, action.tool_name, action.target_id, action.observed_revision
                )
            except ConsentError as error:
                raise ActionError("invalid_consent", str(error)) from error
            if not self._repository.consume_confirmation(
                action.id, ticket_digest=digest, consumed_at=_now()
            ):
                raise ActionError(
                    "consent_replayed_or_expired", "Consent was already used or expired."
                )
            self._repository.set_status(action.id, status="executing", updated_at=_now())
            try:
                if action.tool_name == "startup.disable_current_user":
                    result = self._adapter.disable(action.target_id, action.observed_revision)
                elif action.tool_name == "startup.restore_current_user":
                    result = self._adapter.restore(action.target_id)
                elif action.tool_name == "process.request_close_current_user":
                    if self._process_adapter is None:
                        raise ToolUnavailableError("Process actions are unavailable.")
                    created_at = datetime.fromisoformat(action.created_at)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=UTC)
                    if (datetime.now(UTC) - created_at).total_seconds() > 30:
                        raise TargetChangedError("Process action plan expired; refresh the target.")
                    result = self._process_adapter.request_close(
                        action.target_id, action.observed_revision
                    )
                elif action.tool_name == "process.terminate_current_user":
                    if self._process_adapter is None:
                        raise ToolUnavailableError("Process actions are unavailable.")
                    created_at = datetime.fromisoformat(action.created_at)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=UTC)
                    if (datetime.now(UTC) - created_at).total_seconds() > 30:
                        raise TargetChangedError("Termination plan expired; refresh the target.")
                    result = self._process_adapter.terminate(
                        action.target_id, action.observed_revision
                    )
                else:
                    raise ToolUnavailableError("Action tool is not registered.")
                self._repository.set_status(action.id, status="verifying", updated_at=_now())
                if action.tool_name == "startup.restore_current_user":
                    self._repository.consume_recovery(action.target_id, consumed_at=_now())
                if result.outcome == "close_pending":
                    return self._repository.set_status(
                        action.id,
                        status="close_pending",
                        updated_at=_now(),
                        error_code="close_pending",
                        error_message="The application did not close within the bounded wait.",
                    )
                return self._repository.set_status(
                    action.id, status="succeeded", updated_at=_now(), recovery_id=result.recovery_id
                )
            except ActionVerificationError as error:
                return self._repository.set_status(
                    action.id,
                    status="verification_failed",
                    updated_at=_now(),
                    recovery_id=error.recovery_id,
                    error_code="verification_failed",
                    error_message=str(error),
                )
            except TargetChangedError as error:
                return self._repository.set_status(
                    action.id,
                    status="target_changed",
                    updated_at=_now(),
                    error_code="target_changed",
                    error_message=str(error),
                )
            except ToolPermissionError as error:
                return self._repository.set_status(
                    action.id,
                    status="failed",
                    updated_at=_now(),
                    error_code="permission_required",
                    error_message=str(error),
                )
            except ToolUnavailableError as error:
                return self._repository.set_status(
                    action.id,
                    status="verification_failed",
                    updated_at=_now(),
                    error_code="verification_failed",
                    error_message=str(error),
                )
            except OSError:
                return self._repository.set_status(
                    action.id,
                    status="failed",
                    updated_at=_now(),
                    error_code="bounded_os_error",
                    error_message="Windows could not complete the bounded action.",
                )
            except Exception:
                # The confirmation is already consumed; the action must always reach a
                # terminal state instead of staying "executing" until the next restart.
                return self._repository.set_status(
                    action.id,
                    status="failed",
                    updated_at=_now(),
                    error_code="action_failed",
                    error_message="受控动作未完成，系统没有改变；请重新生成计划。",
                )

    def get(self, action_id: str) -> ActionRecord | None:
        return self._repository.get(action_id)

    def recent(self) -> list[ActionRecord]:
        return self._repository.recent()

    def recover_interrupted(self) -> int:
        return self._repository.mark_interrupted(_now())

    def shutdown(self) -> None:
        self._repository.close()

    def _required(self, action_id: str) -> ActionRecord:
        action = self._repository.get(action_id)
        if action is None:
            raise ActionError("action_not_found", "Action not found.")
        return action

    @staticmethod
    def _age_seconds(action: ActionRecord) -> float:
        created_at = datetime.fromisoformat(action.created_at)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return (datetime.now(UTC) - created_at).total_seconds()
