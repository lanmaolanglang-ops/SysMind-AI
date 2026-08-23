from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from threading import Event
from typing import cast

from sysmind.application.ports.diagnoses import DiagnosisRepository
from sysmind.diagnosis.planning import classify_question, plan_for
from sysmind.diagnosis.rules import build_findings
from sysmind.domain.diagnosis import DiagnosisRecord, DiagnosisToolCall
from sysmind.prompts.report_explainer import LocalReportExplainer, ReportExplainer
from sysmind.reports import compose_report, render_markdown
from sysmind.reports.evidence import evidence_path_exists
from sysmind.tools.executor import ToolExecutor, arguments_hash
from sysmind.tools.policy import ToolPolicy
from sysmind.tools.registry import ToolRegistry


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DiagnosisCoordinator:
    def __init__(
        self,
        repository: DiagnosisRepository,
        registry: ToolRegistry,
        explainer_factory: Callable[[], ReportExplainer] = LocalReportExplainer,
        *,
        max_concurrent: int = 2,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._explainer_factory = explainer_factory
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancellations: dict[str, Event] = {}

    def start(self, question: str) -> DiagnosisRecord:
        category, classified = classify_question(question)
        plan = plan_for(category)
        explainer = self._explainer_factory()
        plan_data: tuple[dict[str, object], ...] = tuple(
            {"tool": step.tool, "arguments": step.arguments, "purpose": step.purpose}
            for step in plan
        )
        diagnosis_id = str(uuid.uuid4())
        record = self._repository.create(
            diagnosis_id=diagnosis_id,
            question=question,
            category=category,
            provider=explainer.name,
            plan=plan_data,
            created_at=_now(),
        )
        cancellation = Event()
        self._cancellations[diagnosis_id] = cancellation
        task = asyncio.create_task(
            self._run(record, plan_data, classified, explainer, cancellation),
            name=f"diagnosis-{diagnosis_id}",
        )
        self._tasks[diagnosis_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(diagnosis_id, None))
        return record

    def get(self, diagnosis_id: str) -> DiagnosisRecord | None:
        return self._repository.get(diagnosis_id)

    def recent(self, limit: int = 20) -> list[DiagnosisRecord]:
        return self._repository.recent(limit)

    def cancel(self, diagnosis_id: str) -> DiagnosisRecord | None:
        record = self._repository.get(diagnosis_id)
        if record and record.status in {"queued", "running"}:
            cancellation = self._cancellations.get(diagnosis_id)
            if cancellation:
                cancellation.set()
        return record

    def feedback(self, diagnosis_id: str, helpful: bool, comment: str | None) -> None:
        self._repository.add_feedback(diagnosis_id, helpful, comment, _now())

    def tool_calls(self, diagnosis_id: str) -> tuple[DiagnosisToolCall, ...]:
        return self._repository.tool_calls(diagnosis_id)

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
        plan: tuple[dict[str, object], ...],
        classified: bool,
        explainer: ReportExplainer,
        cancellation: Event,
    ) -> None:
        try:
            async with self._semaphore, asyncio.timeout(45):
                executor = ToolExecutor(
                    ToolPolicy(self._registry, ("read_only", "network")), max_parallel=1
                )
                allowed = tuple(str(step["tool"]) for step in plan)
                self._repository.update_progress(
                    record.id, status="running", progress=5, current_step="准备诊断计划"
                )
                for index, step in enumerate(plan):
                    if cancellation.is_set():
                        raise asyncio.CancelledError
                    qualified = str(step["tool"])
                    name, version = qualified.rsplit("@", 1)
                    arguments = dict(cast(dict[str, object], step["arguments"]))
                    call_id = str(uuid.uuid4())
                    self._repository.update_progress(
                        record.id,
                        status="running",
                        progress=10 + round(index * 65 / len(plan)),
                        current_step=str(step["purpose"]),
                    )
                    self._repository.create_tool_call(
                        call_id=call_id,
                        diagnosis_id=record.id,
                        tool_name=name,
                        tool_version=version,
                        arguments=arguments,
                        arguments_hash=arguments_hash(arguments),
                        started_at=_now(),
                    )
                    result = await executor.execute(
                        name=name,
                        version=version,
                        arguments=arguments,
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
                if cancellation.is_set():
                    raise asyncio.CancelledError
                calls = self._repository.tool_calls(record.id)
                findings = build_findings(record.category, calls)
                limitations = [
                    f"工具 {call.tool_name}@{call.tool_version} 未完成：{call.error_code}"
                    for call in calls
                    if call.status != "completed"
                ]
                if not classified:
                    limitations.append("问题类型不明确，已采用性能诊断模板；建议补充具体症状。")
                self._repository.update_progress(
                    record.id, status="running", progress=85, current_step="组合证据与解释"
                )
                explanation_started = time.monotonic()
                explanation_request_hash = explainer.request_hash(
                    record.category, record.user_question, findings
                )
                try:
                    explanation = await asyncio.wait_for(
                        explainer.explain(record.category, record.user_question, findings),
                        timeout=8,
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
                        record.category, record.user_question, findings
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
                report = compose_report(record.category, findings, tuple(limitations), explanation)
                valid_calls = {
                    call.id: call.result
                    for call in calls
                    if call.status == "completed" and call.result is not None
                }
                if any(
                    ref.tool_call_id not in valid_calls
                    or not evidence_path_exists(valid_calls[ref.tool_call_id], ref.field_path)
                    for finding in report.findings
                    for ref in finding.evidence
                ):
                    raise ValueError("Report contains an invalid evidence reference.")
                self._repository.complete(
                    record.id,
                    status="partial" if limitations else "completed",
                    report=report,
                    markdown=render_markdown(report),
                    completed_at=_now(),
                )
        except asyncio.CancelledError:
            self._repository.fail(
                record.id,
                status="cancelled",
                code="cancelled",
                message="诊断已取消。",
                completed_at=_now(),
            )
        except TimeoutError:
            self._repository.fail(
                record.id,
                status="failed",
                code="timeout",
                message="诊断超过 45 秒限制。",
                completed_at=_now(),
            )
        except Exception:
            self._repository.fail(
                record.id,
                status="failed",
                code="internal_error",
                message="诊断失败，未暴露敏感错误细节。",
                completed_at=_now(),
            )
        finally:
            self._cancellations.pop(record.id, None)
