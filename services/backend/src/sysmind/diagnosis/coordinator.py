from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event
from typing import cast

from sysmind.agent.planning import (
    DiagnosisPlan,
    DiagnosisPlanner,
    DiagnosisPlannerError,
    DiagnosisPlanStep,
    FakeDiagnosisPlanner,
    PlanPayload,
    validate_plan,
)
from sysmind.application.ports.diagnoses import DiagnosisRepository
from sysmind.application.ports.state_conflict import StateConflict
from sysmind.diagnosis.hypotheses import HypothesisEngine
from sysmind.diagnosis.planning import classify_question
from sysmind.diagnosis.rules import build_findings
from sysmind.domain.diagnosis import (
    DiagnosisRecord,
    DiagnosisReport,
    DiagnosisStatus,
    DiagnosisToolCall,
    StopReason,
    diagnostic_findings,
)
from sysmind.observability.logging import log_event
from sysmind.prompts.report_explainer import LocalReportExplainer, ReportExplainer
from sysmind.reports import compose_report, render_markdown
from sysmind.reports.evidence import evidence_path_exists
from sysmind.security.redaction import redact_arguments
from sysmind.tools.executor import ToolExecutor, arguments_hash
from sysmind.tools.policy import ToolPolicy
from sysmind.tools.registry import ToolRegistry

_LOGGER = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _planner_stop_reason(code: str) -> StopReason:
    """Map planner failures without overstating safety risk.

    ``risk_limit_reached`` covers policy/tool allowlist refusals (including
    ``invalid_plan`` when the plan names a non-read-only tool). Provider and
    transport failures are ``internal_error``; only explicit budget codes map
    to ``budget_exceeded``.
    """
    if code == "plan_budget_exceeded":
        return "budget_exceeded"
    if code.startswith("provider_"):
        return "internal_error"
    return "risk_limit_reached"


class DiagnosisCoordinator:
    def __init__(
        self,
        repository: DiagnosisRepository,
        registry: ToolRegistry,
        explainer_factory: Callable[[], ReportExplainer] = LocalReportExplainer,
        planner_factory: Callable[[], DiagnosisPlanner] | None = None,
        *,
        max_concurrent: int = 2,
        active_timeout_seconds: float = 45,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._explainer_factory = explainer_factory
        self._planner_factory = planner_factory or (lambda: FakeDiagnosisPlanner(registry))
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_timeout_seconds = active_timeout_seconds
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancellations: dict[str, Event] = {}

    def start(self, question: str, *, correlation_id: str | None = None) -> DiagnosisRecord:
        category, classified = classify_question(question)
        planner = self._planner_factory()
        diagnosis_id = str(uuid.uuid4())
        record = self._repository.create(
            diagnosis_id=diagnosis_id,
            question=question,
            category=category,
            provider=planner.name,
            plan=(),
            created_at=_now(),
        )
        log_event(
            _LOGGER,
            logging.INFO,
            "Diagnosis started.",
            component="diagnosis",
            event_type="diagnosis_started",
            diagnosis_id=diagnosis_id,
            correlation_id=correlation_id,
        )
        self._schedule(record, classified, planner, self._explainer_factory())
        return record

    def continue_with_input(self, diagnosis_id: str, answer: str) -> DiagnosisRecord | None:
        record = self._repository.resume_with_input(
            diagnosis_id, input_text=answer, created_at=_now()
        )
        if record is None:
            return None
        question = self._question_with_inputs(record)
        _, classified = classify_question(question)
        self._schedule(record, classified, self._planner_factory(), self._explainer_factory())
        return record

    def _schedule(
        self,
        record: DiagnosisRecord,
        classified: bool,
        planner: DiagnosisPlanner,
        explainer: ReportExplainer,
    ) -> None:
        cancellation = Event()
        self._cancellations[record.id] = cancellation
        task = asyncio.create_task(
            self._run(record, classified, planner, explainer, cancellation),
            name=f"diagnosis-{record.id}",
        )
        self._tasks[record.id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(record.id, None))

    def get(self, diagnosis_id: str) -> DiagnosisRecord | None:
        return self._repository.get(diagnosis_id)

    def recent(self, limit: int = 20) -> list[DiagnosisRecord]:
        return self._repository.recent(limit)

    def cancel(self, diagnosis_id: str) -> DiagnosisRecord | None:
        record = self._repository.get(diagnosis_id)
        if record is None:
            return None
        if record.status in {"queued", "running"}:
            cancellation = self._cancellations.get(diagnosis_id)
            if cancellation:
                cancellation.set()
        elif record.status == "waiting_user_input":
            self._stop_and_fail(
                diagnosis_id,
                reason="user_cancelled",
                status="cancelled",
                code="cancelled",
                message="诊断已取消。",
            )
        return record

    def feedback(self, diagnosis_id: str, helpful: bool, comment: str | None) -> None:
        self._repository.add_feedback(diagnosis_id, helpful, comment, _now())

    def tool_calls(self, diagnosis_id: str) -> tuple[DiagnosisToolCall, ...]:
        return self._repository.tool_calls(diagnosis_id)

    def user_inputs(self, diagnosis_id: str) -> tuple[str, ...]:
        return self._repository.user_inputs(diagnosis_id)

    def recover_interrupted(self) -> int:
        return self._repository.mark_interrupted(_now())

    async def shutdown(self) -> None:
        for cancellation in self._cancellations.values():
            cancellation.set()
        if self._tasks:
            _, pending = await asyncio.wait(tuple(self._tasks.values()), timeout=2.5)
            for task in pending:
                task.cancel()

    async def _run(
        self,
        record: DiagnosisRecord,
        classified: bool,
        planner: DiagnosisPlanner,
        explainer: ReportExplainer,
        cancellation: Event,
    ) -> None:
        try:
            async with self._semaphore, asyncio.timeout(self._active_timeout_seconds):
                await self._run_bounded(record, classified, planner, explainer, cancellation)
        except asyncio.CancelledError:
            self._stop_and_fail(
                record.id,
                reason="user_cancelled",
                status="cancelled",
                code="cancelled",
                message="诊断已取消。",
            )
        except DiagnosisPlannerError as error:
            # Map planner failures accurately. Only an actual safety refusal is
            # `risk_limit_reached`; budget and protocol/validation failures must
            # not masquerade as a risk-limit stop.
            reason: StopReason = _planner_stop_reason(error.code)
            self._stop_and_fail(
                record.id,
                reason=reason,
                status="failed",
                code=error.code,
                message=str(error),
            )
        except TimeoutError:
            self._stop_and_fail(
                record.id,
                reason="budget_exceeded",
                status="failed",
                code="timeout",
                message=f"诊断超过 {self._active_timeout_seconds:g} 秒限制。",
            )
        except Exception:
            # Unexpected bugs are not a safety risk-limit event.
            self._stop_and_fail(
                record.id,
                reason="internal_error",
                status="failed",
                code="internal_error",
                message="诊断失败，未暴露敏感错误细节。",
            )
        finally:
            self._cancellations.pop(record.id, None)

    async def _run_bounded(
        self,
        record: DiagnosisRecord,
        classified: bool,
        planner: DiagnosisPlanner,
        explainer: ReportExplainer,
        cancellation: Event,
    ) -> None:
        self._repository.update_progress(
            record.id,
            status="running",
            progress=max(2, record.progress),
            current_step="正在确定需要检查的项目",
        )
        question = self._question_with_inputs(record)
        existing_calls = self._repository.tool_calls(record.id)
        current_plan = self._restore_plan(record) if existing_calls else None
        latest_plan_id: str | None = None
        revision = record.agent_round_count
        executor = ToolExecutor(
            ToolPolicy(self._registry, ("read_only", "network")), max_parallel=1
        )
        budget_stop = False

        while revision < record.max_agent_rounds:
            if cancellation.is_set():
                raise asyncio.CancelledError
            calls = self._repository.tool_calls(record.id)
            if len(calls) >= record.max_tool_calls:
                budget_stop = True
                break
            if current_plan is None:
                try:
                    plan = await planner.create_plan(question)
                except DiagnosisPlannerError as error:
                    # Provider/protocol failures should still allow a read-only
                    # local plan so evidence collection can complete. Policy
                    # refusals and budget errors still fail closed.
                    if error.code in {"provider_error", "provider_protocol_error"}:
                        log_event(
                            _LOGGER,
                            logging.WARNING,
                            "Planner failed; falling back to local read-only plan.",
                            component="diagnosis",
                            event_type="diagnosis_planner_fallback",
                            diagnosis_id=record.id,
                            error_code=error.code,
                        )
                        self._repository.add_agent_decision(
                            record.id,
                            plan_id=None,
                            decision_type="planner_fallback",
                            reason="模型规划失败，改用本地只读诊断计划",
                            data={"error_code": error.code},
                            created_at=_now(),
                        )
                        plan = await FakeDiagnosisPlanner(self._registry).create_plan(question)
                        planner = FakeDiagnosisPlanner(self._registry)
                    else:
                        raise
            else:
                candidate = await planner.revise_plan(question, current_plan, calls)
                if candidate is None:
                    break
                plan = candidate
            plan = validate_plan(PlanPayload.model_validate(plan.as_dict()), self._registry)
            revision += 1
            latest_plan_id, step_ids = self._save_plan(record.id, planner, plan, revision=revision)
            current_plan = plan
            if plan.status == "ask_user":
                clarification = plan.clarification_question or "请补充更具体的问题现象。"
                self._repository.add_agent_decision(
                    record.id,
                    plan_id=latest_plan_id,
                    decision_type="ask_user",
                    reason="当前证据不足以安全选择下一步工具",
                    data={"question": clarification, "round": revision},
                    created_at=_now(),
                )
                self._repository.record_stop_reason(
                    record.id,
                    reason="insufficient_information",
                    detail="Agent 请求用户补充诊断所需信息。",
                    terminal_status="waiting_user_input",
                    created_at=_now(),
                )
                try:
                    self._repository.wait_for_input(record.id, question=clarification)
                except StateConflict:
                    # Cancel/timeout won while the plan was being written.
                    log_event(
                        _LOGGER,
                        logging.INFO,
                        "Diagnosis wait_for_input lost the state race.",
                        component="diagnosis",
                        event_type="diagnosis_state_conflict",
                        diagnosis_id=record.id,
                    )
                return
            if plan.status == "complete":
                break

            fresh_steps, fresh_step_ids = self._filter_completed_steps(
                record.id, plan.steps, step_ids, calls, latest_plan_id
            )
            if len(calls) + len(fresh_steps) > record.max_tool_calls:
                budget_stop = True
                self._repository.add_agent_decision(
                    record.id,
                    plan_id=latest_plan_id,
                    decision_type="budget_stop",
                    reason="下一轮工具会超过诊断预算，保留已有证据并停止",
                    data={"tool_call_count": len(calls), "max_tool_calls": record.max_tool_calls},
                    created_at=_now(),
                )
                break
            if fresh_steps:
                progress_start = min(70, 8 + (revision - 1) * 18)
                await self._execute_steps(
                    record.id,
                    list(fresh_steps),
                    fresh_step_ids,
                    tuple(step.tool for step in fresh_steps),
                    executor,
                    cancellation,
                    progress_start=progress_start,
                    progress_span=16,
                )
                self._persist_current_hypotheses(record.id)
            else:
                self._repository.add_agent_decision(
                    record.id,
                    plan_id=latest_plan_id,
                    decision_type="duplicate_fuse",
                    reason="本轮计划没有新的可执行工具，停止重复循环",
                    data={"round": revision},
                    created_at=_now(),
                )
                break
        else:
            budget_stop = True

        await self._finalize(
            record,
            question,
            classified,
            explainer,
            latest_plan_id,
            cancellation,
            stop_reason_override="budget_exceeded" if budget_stop else None,
        )

    def _filter_completed_steps(
        self,
        diagnosis_id: str,
        steps: tuple[DiagnosisPlanStep, ...],
        step_ids: tuple[str, ...],
        calls: tuple[DiagnosisToolCall, ...],
        plan_id: str,
    ) -> tuple[tuple[DiagnosisPlanStep, ...], tuple[str, ...]]:
        completed = {
            f"{call.tool_name}@{call.tool_version}": call.id
            for call in calls
            if call.status == "completed"
        }
        fresh_steps: list[DiagnosisPlanStep] = []
        fresh_ids: list[str] = []
        for step, step_id in zip(steps, step_ids, strict=True):
            existing_call_id = completed.get(step.tool)
            if existing_call_id is None:
                fresh_steps.append(step)
                fresh_ids.append(step_id)
                continue
            self._repository.finish_diagnosis_step(
                step_id, status="skipped_duplicate", tool_call_id=existing_call_id
            )
            self._repository.add_agent_decision(
                diagnosis_id,
                plan_id=plan_id,
                decision_type="duplicate_tool_skipped",
                reason="已完成的只读工具不会在续接任务中重复执行",
                data={"tool": step.tool, "tool_call_id": existing_call_id},
                created_at=_now(),
            )
        return tuple(fresh_steps), tuple(fresh_ids)

    async def _finalize(
        self,
        record: DiagnosisRecord,
        question: str,
        classified: bool,
        explainer: ReportExplainer,
        plan_id: str | None,
        cancellation: Event,
        *,
        stop_reason_override: StopReason | None = None,
    ) -> None:
        if cancellation.is_set():
            raise asyncio.CancelledError
        calls = self._repository.tool_calls(record.id)
        current_record = self._repository.get(record.id) or record
        findings = build_findings(current_record.category, calls)
        conclusions = diagnostic_findings(findings)
        hypotheses = HypothesisEngine().build(
            current_record.category, findings, calls, diagnosis_id=record.id
        )
        self._repository.replace_hypotheses(record.id, hypotheses=hypotheses, updated_at=_now())
        limitations = [
            f"工具 {call.tool_name}@{call.tool_version} 未完成：{call.error_code}"
            for call in calls
            if call.status != "completed"
        ]
        if not classified:
            limitations.append("问题类型不明确，Agent 按最可能类别规划；建议补充具体症状。")
        startup_question = any(word in question.casefold() for word in ("开机", "启动"))
        startup_conclusion = any(
            finding.code == "large_startup_inventory" for finding in conclusions
        )
        confidence_cap = 1.0 if classified else 0.65
        if startup_question and not startup_conclusion:
            limitations.append(
                "启动项检查未形成异常结论；当前高占用等快照只能说明检查时状态，"
                "不能证明它导致开机缓慢。"
            )
            confidence_cap = min(confidence_cap, 0.6)
        gaming_question = any(
            word in question.casefold() for word in ("游戏", "掉帧", "gpu", "显卡")
        )
        if gaming_question and any(finding.code == "gpu_metadata_only" for finding in findings):
            limitations.append(
                "当前只能读取显卡与驱动信息，没有 GPU 实时负载或显存压力证据；"
                "当前资源快照不能单独确定掉帧原因。"
            )
            confidence_cap = min(confidence_cap, 0.6)
        generic_crash_question = question.casefold().strip() in {
            "软件一直闪退",
            "软件总是闪退",
            "应用一直闪退",
            "应用总是闪退",
        }
        if generic_crash_question and conclusions:
            limitations.append(
                "问题中没有具体应用名称；近期崩溃记录可能与描述的软件无关，"
                "请核对报告中的应用和发生时间。"
            )
            confidence_cap = min(confidence_cap, 0.65)
        if (
            current_record.category == "network"
            and conclusions
            and all(finding.code == "network_packet_loss" for finding in conclusions)
        ):
            limitations.append(
                "当前异常仅来自固定目标 ICMP 测试；目标可能限制响应，"
                "该结果不能单独确定无法联网的原因。"
            )
            confidence_cap = min(confidence_cap, 0.65)
        completed_calls = tuple(
            call for call in calls if call.status == "completed" and call.result is not None
        )
        stop_reason: StopReason = stop_reason_override or (
            "evidence_sufficient" if conclusions else "insufficient_information"
        )
        if not conclusions:
            limitations.append("已完成的检查未达到确定性规则阈值；建议在问题复现时重新诊断。")
        if stop_reason == "budget_exceeded":
            limitations.append("诊断已达到安全预算，未继续增加检查轮次或工具调用。")
        self._repository.update_progress(
            record.id, status="running", progress=85, current_step="正在整理证据并生成报告"
        )
        explanation_started = time.monotonic()
        explanation_request_hash = explainer.request_hash(
            current_record.category, question, conclusions
        )
        try:
            explanation = await asyncio.wait_for(
                explainer.explain(current_record.category, question, conclusions), timeout=8
            )
        except Exception:
            if explainer.name != "local-rules":
                self._repository.add_model_call(
                    record.id,
                    provider=explainer.name,
                    status="failed",
                    request_hash=cast(str, explanation_request_hash),
                    response_hash=None,
                    duration_ms=round((time.monotonic() - explanation_started) * 1000),
                    error_code="provider_error",
                    created_at=_now(),
                )
            limitations.append("模型解释不可用，报告已降级为本地规则结果。")
            explanation = await LocalReportExplainer().explain(
                current_record.category, question, conclusions
            )
        else:
            if explainer.name != "local-rules":
                self._repository.add_model_call(
                    record.id,
                    provider=explainer.name,
                    status="completed",
                    request_hash=cast(str, explanation_request_hash),
                    response_hash=hashlib.sha256(explanation.encode()).hexdigest(),
                    duration_ms=round((time.monotonic() - explanation_started) * 1000),
                    error_code=None,
                    created_at=_now(),
                )
        report = compose_report(
            current_record.category,
            findings,
            tuple(limitations),
            explanation,
            hypotheses=hypotheses,
            evidence_coverage=len(completed_calls) / max(1, len(calls)),
            confidence_cap=confidence_cap,
        )
        self._validate_report_evidence(report, calls)
        self._repository.add_agent_decision(
            record.id,
            plan_id=plan_id,
            decision_type="finalize",
            reason="所有结论与假设均已通过工具调用及字段路径证据校验",
            data={
                "finding_count": len(report.findings),
                "hypothesis_count": len(report.hypotheses),
                "stop_reason": stop_reason,
            },
            created_at=_now(),
        )
        final_status: DiagnosisStatus = (
            "partial" if limitations or stop_reason != "evidence_sufficient" else "completed"
        )
        stop_details = {
            "evidence_sufficient": "现有本机证据已形成至少一个确定性诊断结论。",
            "insufficient_information": "当前证据不足，无法确定原因。",
            "budget_exceeded": "诊断达到安全预算，已使用现有证据生成报告。",
            "user_cancelled": "诊断已由用户取消。",
            "risk_limit_reached": "诊断计划包含超出当前安全范围的操作，已停止。",
            "backend_restarted": "本地服务重启，诊断已中断。",
            "internal_error": "诊断过程中出现内部错误，已安全停止。",
        }
        self._repository.record_stop_reason(
            record.id,
            reason=stop_reason,
            detail=stop_details.get(stop_reason, "诊断已停止。"),
            terminal_status=final_status,
            created_at=_now(),
        )
        try:
            self._repository.complete(
                record.id,
                status=final_status,
                report=report,
                markdown=render_markdown(report, calls),
                completed_at=_now(),
            )
        except StateConflict:
            # Cancel/timeout already finalized this diagnosis; keep their result.
            log_event(
                _LOGGER,
                logging.INFO,
                "Diagnosis finalize lost the terminal-state race.",
                component="diagnosis",
                event_type="diagnosis_state_conflict",
                diagnosis_id=record.id,
                requested_status=final_status,
            )

    def _persist_current_hypotheses(self, diagnosis_id: str) -> None:
        record = self._repository.get(diagnosis_id)
        if record is None:
            raise KeyError(diagnosis_id)
        calls = self._repository.tool_calls(diagnosis_id)
        findings = build_findings(record.category, calls)
        hypotheses = HypothesisEngine().build(
            record.category, findings, calls, diagnosis_id=diagnosis_id
        )
        self._repository.replace_hypotheses(diagnosis_id, hypotheses=hypotheses, updated_at=_now())

    @staticmethod
    def _validate_report_evidence(
        report: DiagnosisReport, calls: tuple[DiagnosisToolCall, ...]
    ) -> None:
        valid_calls = {
            call.id: call.result
            for call in calls
            if call.status == "completed" and call.result is not None
        }
        references = [ref for finding in report.findings for ref in finding.evidence] + [
            ref
            for hypothesis in report.hypotheses
            for ref in hypothesis.supporting_evidence + hypothesis.contradicting_evidence
        ]
        if any(
            ref.tool_call_id not in valid_calls
            or not evidence_path_exists(valid_calls[ref.tool_call_id], ref.field_path)
            for ref in references
        ):
            raise ValueError("Report contains an invalid evidence reference.")

    def _question_with_inputs(self, record: DiagnosisRecord) -> str:
        inputs = self._repository.user_inputs(record.id)
        if not inputs:
            return record.user_question
        additions = "；".join(item[:500] for item in inputs[-4:])
        return f"{record.user_question}\n用户补充：{additions}"

    @staticmethod
    def _restore_plan(record: DiagnosisRecord) -> DiagnosisPlan:
        steps = tuple(
            DiagnosisPlanStep(
                tool=str(item["tool"]),
                reason=str(item.get("reason") or item.get("purpose") or "继续已有诊断步骤"),
                arguments=cast(dict[str, object], item.get("arguments", {})),
            )
            for item in record.plan
        )
        return DiagnosisPlan(
            record.category,
            record.plan_confidence or 0.5,
            steps,
            "ready",
        )

    def _stop_and_fail(
        self,
        diagnosis_id: str,
        *,
        reason: StopReason,
        status: DiagnosisStatus,
        code: str,
        message: str,
    ) -> None:
        current = self._repository.get(diagnosis_id)
        if current is None or current.status in {
            "completed",
            "partial",
            "cancelled",
            "failed",
            "interrupted",
        }:
            return
        timestamp = _now()
        self._repository.record_stop_reason(
            diagnosis_id,
            reason=reason,
            detail=message,
            terminal_status=status,
            created_at=timestamp,
        )
        try:
            self._repository.fail(
                diagnosis_id,
                status=status,
                code=code,
                message=message,
                completed_at=timestamp,
            )
        except StateConflict:
            # A concurrent terminalizer already won (e.g. cancel vs timeout).
            log_event(
                _LOGGER,
                logging.INFO,
                "Diagnosis already reached a terminal state.",
                component="diagnosis",
                event_type="diagnosis_state_conflict",
                diagnosis_id=diagnosis_id,
                requested_status=status,
            )

    def _save_plan(
        self,
        diagnosis_id: str,
        planner: DiagnosisPlanner,
        plan: DiagnosisPlan,
        *,
        revision: int,
    ) -> tuple[str, tuple[str, ...]]:
        plan_id, step_ids = self._repository.save_agent_plan(
            diagnosis_id,
            provider=planner.name,
            plan=plan.as_dict(),
            revision=revision,
            created_at=_now(),
        )
        self._repository.add_agent_decision(
            diagnosis_id,
            plan_id=plan_id,
            decision_type="plan_created" if revision == 1 else "plan_revised",
            reason="; ".join(step.reason for step in plan.steps) or "需要用户补充信息",
            data={
                "problem_category": plan.problem_category,
                "confidence": plan.confidence,
                "tool_count": len(plan.steps),
                "round": revision,
            },
            created_at=_now(),
        )
        return plan_id, step_ids

    async def _execute_steps(
        self,
        diagnosis_id: str,
        steps: list[DiagnosisPlanStep],
        step_ids: tuple[str, ...],
        allowed: tuple[str, ...],
        executor: ToolExecutor,
        cancellation: Event,
        *,
        progress_start: int,
        progress_span: int,
    ) -> None:
        for index, step in enumerate(steps):
            if cancellation.is_set():
                raise asyncio.CancelledError
            parts = step.tool.rsplit("@", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                name, version = parts
            else:
                name, version = step.tool, "1.0"
            call_id = str(uuid.uuid4())
            self._repository.update_progress(
                diagnosis_id,
                status="running",
                progress=progress_start + round(index * progress_span / max(1, len(steps))),
                current_step=step.reason,
            )
            self._repository.create_tool_call(
                call_id=call_id,
                diagnosis_id=diagnosis_id,
                tool_name=name,
                tool_version=version,
                # Only the redacted copy is persisted; raw arguments never reach storage.
                redacted_arguments=redact_arguments(step.arguments),
                arguments_hash=arguments_hash(step.arguments),
                started_at=_now(),
            )
            result = await executor.execute(
                name=name,
                version=version,
                arguments=step.arguments,
                allowed_tools=allowed,
                cancel_event=cancellation,
            )
            self._repository.finish_tool_call(
                call_id,
                status=result.status,
                result=result.full_result,
                summary=result.summary,
                error_code=result.error_code,
                error_message=result.error_message,
                duration_ms=result.duration_ms,
                finished_at=_now(),
            )
            self._repository.finish_diagnosis_step(
                step_ids[index], status=result.status, tool_call_id=call_id
            )
