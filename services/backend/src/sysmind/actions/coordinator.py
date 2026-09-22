from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

from sysmind.application.ports.actions import (
    ActionRepository,
    ActionStateConflict,
    ActionVerificationError,
    ProcessActionAdapter,
    StartupActionAdapter,
    TargetChangedError,
)
from sysmind.application.ports.diagnoses import DiagnosisRepository
from sysmind.domain.actions import (
    CLOSE_PROCESS_TOOL,
    DISABLE_STARTUP_TOOL,
    RESTORE_STARTUP_TOOL,
    TERMINATE_PROCESS_TOOL,
    ActionRecord,
    ActionStatus,
    ProcessActionCandidate,
    StartupActionCandidate,
    action_tool_version,
)
from sysmind.security import ConsentError, ConsentService
from sysmind.security.redaction import redact_text
from sysmind.tools.contracts import ToolPermissionError, ToolUnavailableError

# Bounded execution window for process actions; the consent ticket TTL is capped to the
# remaining window so a user is never handed a ticket that outlives its own plan.
PROCESS_PLAN_WINDOW_SECONDS = 30

# Failure text is persisted and shown in the UI, so it is redacted and clamped.
_MAX_ERROR_MESSAGE = 280


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _bounded_error(error: BaseException | str) -> str:
    message = redact_text(str(error)).strip()
    if not message:
        return "受控动作未完成，系统没有改变。"
    return message[:_MAX_ERROR_MESSAGE]


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
        startup_calls = tuple(
            call
            for call in calls
            if call.status == "completed" and call.tool_name in {"startup.list", "startup.analyze"}
        )
        if not startup_calls:
            raise ActionError(
                "startup_evidence_required",
                "This diagnosis contains no completed startup evidence.",
            )
        adapter_candidates = tuple(self._adapter.candidates())
        evidence_ids = self._startup_evidence_ids(diagnosis.report, startup_calls)
        if not evidence_ids:
            raise ActionError(
                "startup_evidence_required",
                "Referenced startup evidence did not contain bound target identities.",
            )
        return tuple(item for item in adapter_candidates if item.item_id in evidence_ids)

    @staticmethod
    def _startup_evidence_ids(
        report: object,
        startup_calls: tuple[object, ...],
    ) -> set[str]:
        referenced = ActionCoordinator._referenced_call_ids(report)
        evidence_ids: set[str] = set()
        for call in startup_calls:
            call_id = getattr(call, "id", None)
            result = getattr(call, "result", None)
            if call_id not in referenced:
                continue
            items: list[object] = []
            if isinstance(result, list):
                items = result
            elif isinstance(result, dict):
                nested = result.get("items")
                if isinstance(nested, list):
                    items = nested
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id")
                if isinstance(item_id, str) and item_id:
                    evidence_ids.add(item_id)
        return evidence_ids

    @staticmethod
    def _referenced_call_ids(report: object) -> set[str]:
        referenced: set[str] = set()
        findings = getattr(report, "findings", ()) if report is not None else ()
        hypotheses = getattr(report, "hypotheses", ()) if report is not None else ()
        for finding in findings:
            for evidence in finding.evidence:
                referenced.add(evidence.tool_call_id)
        for hypothesis in hypotheses:
            for evidence in hypothesis.supporting_evidence:
                referenced.add(evidence.tool_call_id)
            for evidence in hypothesis.contradicting_evidence:
                referenced.add(evidence.tool_call_id)
        return referenced

    def create_disable(
        self, diagnosis_id: str, item_id: str, observed_revision: str
    ) -> ActionRecord:
        target = next(
            (item for item in self.candidates(diagnosis_id) if item.item_id == item_id),
            None,
        )
        if target is None or target.observed_revision != observed_revision:
            raise ActionError("target_changed", "Startup target changed; refresh the plan.")
        return self._repository.create(
            plan_id=str(uuid.uuid4()),
            action_id=str(uuid.uuid4()),
            diagnosis_id=diagnosis_id,
            tool_name=DISABLE_STARTUP_TOOL,
            tool_version=action_tool_version(DISABLE_STARTUP_TOOL),
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
        referenced_call_ids = self._referenced_call_ids(diagnosis.report)
        evidence_item_ids: set[str] = set()
        for call in calls:
            if call.id not in referenced_call_ids or not isinstance(call.result, list):
                continue
            for item in call.result:
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id")
                if isinstance(item_id, str) and item_id:
                    evidence_item_ids.add(item_id)
        if not evidence_item_ids:
            raise ActionError(
                "process_evidence_required",
                "Referenced process evidence did not contain bound target identities.",
            )
        candidates = tuple(self._process_adapter.candidates())
        return tuple(item for item in candidates if item.item_id in evidence_item_ids)

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
            tool_name=CLOSE_PROCESS_TOOL,
            tool_version=action_tool_version(CLOSE_PROCESS_TOOL),
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
        # Fail closed when the process instance is gone or its observed identity
        # (including create-time / image / handle set) no longer matches the close plan.
        if target is None or target.observed_revision != original.observed_revision:
            raise ActionError("target_changed", "Process is no longer an eligible target.")
        return self._repository.create(
            plan_id=str(uuid.uuid4()),
            action_id=str(uuid.uuid4()),
            diagnosis_id=original.diagnosis_id,
            tool_name=TERMINATE_PROCESS_TOOL,
            tool_version=action_tool_version(TERMINATE_PROCESS_TOOL),
            target=target,
            created_at=_now(),
        )

    def create_restore(self, action_id: str) -> ActionRecord:
        original = self._required(action_id)
        if original.tool_name != DISABLE_STARTUP_TOOL:
            raise ActionError(
                "unsupported_recovery",
                "Only a startup disable action can be restored.",
            )
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
        if action.tool_name == TERMINATE_PROCESS_TOOL and action.status == "proposed":
            now = _now()
            self._repository.add_confirmation_stage(action.id, stage=1, created_at=now)
            action = self._repository.set_status(
                action.id,
                expected_statuses=("proposed",),
                status="awaiting_second_confirmation",
                updated_at=now,
            )
            return action, None, None
        if (
            action.tool_name == TERMINATE_PROCESS_TOOL
            and action.status == "awaiting_second_confirmation"
            and self._age_seconds(action) > PROCESS_PLAN_WINDOW_SECONDS
        ):
            self._repository.set_status(
                action.id,
                expected_statuses=("awaiting_second_confirmation",),
                status="expired",
                updated_at=_now(),
            )
            raise ActionError("action_expired", "Termination confirmation window expired.")
        if action.status not in {"proposed", "awaiting_second_confirmation"}:
            raise ActionError("invalid_action_state", "Only a proposed action can be confirmed.")
        if action.tool_name == TERMINATE_PROCESS_TOOL and (
            action.status == "awaiting_second_confirmation"
        ):
            # Second explicit confirmation for forced termination (audit trail).
            self._repository.add_confirmation_stage(action.id, stage=2, created_at=_now())
        # Process actions also have a bounded execution window; cap the ticket lifetime to
        # whatever remains so the issued expiry matches when the plan can actually run.
        ttl_seconds: int | None = None
        if action.tool_name in {CLOSE_PROCESS_TOOL, TERMINATE_PROCESS_TOOL}:
            remaining = PROCESS_PLAN_WINDOW_SECONDS - self._age_seconds(action)
            ttl_seconds = max(1, int(remaining))
        issued = self._consent.issue(
            action.id,
            action.tool_name,
            action.target_id,
            action.observed_revision,
            ttl_seconds=ttl_seconds,
        )
        self._repository.add_confirmation(
            action.id, ticket_digest=issued.digest, expires_at=issued.expires_at, created_at=_now()
        )
        try:
            action = self._repository.set_status(
                action.id,
                expected_statuses=("proposed", "awaiting_second_confirmation"),
                status="confirmed",
                updated_at=_now(),
            )
        except ActionStateConflict as error:
            raise ActionError(
                "invalid_action_state", "Action state changed concurrently."
            ) from error
        return action, issued.ticket, issued.expires_at

    def reject(self, action_id: str) -> ActionRecord:
        action = self._required(action_id)
        if action.status not in {"proposed", "awaiting_second_confirmation"}:
            raise ActionError("invalid_action_state", "Only a proposed action can be rejected.")
        now = _now()
        self._repository.add_rejection(action.id, created_at=now)
        try:
            return self._repository.set_status(
                action.id,
                expected_statuses=("proposed", "awaiting_second_confirmation"),
                status="rejected",
                updated_at=now,
            )
        except ActionStateConflict as error:
            raise ActionError(
                "invalid_action_state", "Action state changed concurrently."
            ) from error

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
            self._repository.set_status(
                action.id,
                expected_statuses=("confirmed",),
                status="executing",
                updated_at=_now(),
            )
            persisted_status: ActionStatus = "executing"
            try:
                if action.tool_name == DISABLE_STARTUP_TOOL:
                    result = self._adapter.disable(action.target_id, action.observed_revision)
                elif action.tool_name == RESTORE_STARTUP_TOOL:
                    result = self._adapter.restore(action.target_id)
                elif action.tool_name == CLOSE_PROCESS_TOOL:
                    if self._process_adapter is None:
                        raise ToolUnavailableError("Process actions are unavailable.")
                    created_at = datetime.fromisoformat(action.created_at)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=UTC)
                    if (
                        datetime.now(UTC) - created_at
                    ).total_seconds() > PROCESS_PLAN_WINDOW_SECONDS:
                        raise TargetChangedError("Process action plan expired; refresh the target.")
                    result = self._process_adapter.request_close(
                        action.target_id, action.observed_revision
                    )
                elif action.tool_name == TERMINATE_PROCESS_TOOL:
                    if self._process_adapter is None:
                        raise ToolUnavailableError("Process actions are unavailable.")
                    created_at = datetime.fromisoformat(action.created_at)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=UTC)
                    if (
                        datetime.now(UTC) - created_at
                    ).total_seconds() > PROCESS_PLAN_WINDOW_SECONDS:
                        raise TargetChangedError("Termination plan expired; refresh the target.")
                    result = self._process_adapter.terminate(
                        action.target_id, action.observed_revision
                    )
                else:
                    raise ToolUnavailableError("Action tool is not registered.")
                self._repository.set_status(
                    action.id,
                    expected_statuses=("executing",),
                    status="verifying",
                    updated_at=_now(),
                )
                persisted_status = "verifying"
                if action.tool_name == RESTORE_STARTUP_TOOL:
                    self._repository.consume_recovery(action.target_id, consumed_at=_now())
                if result.outcome == "close_pending":
                    return self._repository.set_status(
                        action.id,
                        expected_statuses=("verifying",),
                        status="close_pending",
                        updated_at=_now(),
                        error_code="close_pending",
                        error_message="The application did not close within the bounded wait.",
                    )
                return self._repository.set_status(
                    action.id,
                    expected_statuses=("verifying",),
                    status="succeeded",
                    updated_at=_now(),
                    recovery_id=result.recovery_id,
                )
            except ActionVerificationError as error:
                return self._repository.set_status(
                    action.id,
                    expected_statuses=(persisted_status,),
                    status="verification_failed",
                    updated_at=_now(),
                    recovery_id=error.recovery_id,
                    error_code="verification_failed",
                    error_message=_bounded_error(error),
                )
            except TargetChangedError as error:
                return self._repository.set_status(
                    action.id,
                    expected_statuses=(persisted_status,),
                    status="target_changed",
                    updated_at=_now(),
                    error_code="target_changed",
                    error_message=_bounded_error(error),
                )
            except ToolPermissionError as error:
                return self._repository.set_status(
                    action.id,
                    expected_statuses=(persisted_status,),
                    status="failed",
                    updated_at=_now(),
                    error_code="permission_required",
                    error_message=_bounded_error(error),
                )
            except ToolUnavailableError as error:
                return self._repository.set_status(
                    action.id,
                    expected_statuses=(persisted_status,),
                    status="verification_failed",
                    updated_at=_now(),
                    error_code="verification_failed",
                    error_message=_bounded_error(error),
                )
            except OSError:
                return self._repository.set_status(
                    action.id,
                    expected_statuses=(persisted_status,),
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
                    expected_statuses=(persisted_status,),
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
