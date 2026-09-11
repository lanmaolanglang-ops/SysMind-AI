from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from threading import Event
from typing import Literal

from sysmind.application.ports.scans import ScanRepository
from sysmind.domain.diagnostics import ScanRecord, StepStatus
from sysmind.observability.logging import log_event
from sysmind.tools.contracts import ToolCancelledError, ToolSpec, ToolUnavailableError
from sysmind.tools.executor import arguments_hash
from sysmind.tools.process import PROCESS_TOOL_SPECS, ProcessTools
from sysmind.tools.system import SYSTEM_TOOL_SPECS, SystemTools

SCAN_SCHEMA_VERSION = "1.0"
_LOGGER = logging.getLogger(__name__)

# Quick-scan probes are invoked with no parameters, so their normalized parameter hash is
# the hash of an empty mapping. Recording it keeps the scan audit trail aligned with the
# event-log trail, which always stores an arguments hash.
NO_ARGUMENTS_HASH = arguments_hash({})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def _failure(error: Exception) -> tuple[str, str, StepStatus]:
    if isinstance(error, TimeoutError):
        return "tool_timeout", "采集步骤超时，已跳过该项。", "timed_out"
    if isinstance(error, ToolUnavailableError):
        return "capability_unavailable", str(error), "failed"
    if isinstance(error, ToolCancelledError):
        return "scan_cancelled", "扫描已取消。", "cancelled"
    return "collection_failed", "该项系统信息暂时无法读取。", "failed"


def _result_summary(value: object) -> dict[str, object]:
    summary: dict[str, object] = {"result_type": type(value).__name__}
    if isinstance(value, (list, tuple)):
        summary["item_count"] = len(value)
    return summary


class QuickScanCoordinator:
    def __init__(
        self,
        repository: ScanRepository,
        system_tools: SystemTools,
        process_tools: ProcessTools,
    ) -> None:
        self._repository = repository
        self._system_tools = system_tools
        self._process_tools = process_tools
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancellations: dict[str, Event] = {}

    def start(self, correlation_id: str | None = None) -> ScanRecord:
        scan_id = str(uuid.uuid4())
        record = self._repository.create(scan_id, _now(), SCAN_SCHEMA_VERSION)
        cancellation = Event()
        self._cancellations[scan_id] = cancellation
        task = asyncio.create_task(
            self._run_guarded(scan_id, cancellation, correlation_id),
            name=f"quick-scan-{scan_id}",
        )
        self._tasks[scan_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(scan_id, None))
        return record

    def get(self, scan_id: str) -> ScanRecord | None:
        return self._repository.get(scan_id)

    def recent(self, limit: int = 20) -> list[ScanRecord]:
        return self._repository.recent(limit)

    def recover_interrupted(self) -> int:
        return self._repository.mark_interrupted(_now())

    def cancel(self, scan_id: str) -> ScanRecord | None:
        record = self._repository.get(scan_id)
        if record is None:
            return None
        cancellation = self._cancellations.get(scan_id)
        if cancellation and record.status in {"queued", "running"}:
            cancellation.set()
        return self._repository.get(scan_id)

    async def shutdown(self) -> None:
        for cancellation in self._cancellations.values():
            cancellation.set()
        if not self._tasks:
            return
        _, pending = await asyncio.wait(tuple(self._tasks.values()), timeout=2.5)
        for task in pending:
            task.cancel()

    async def _run(self, scan_id: str, cancellation: Event, correlation_id: str | None) -> None:
        specs = {spec.name: spec for spec in (*SYSTEM_TOOL_SPECS, *PROCESS_TOOL_SPECS)}
        handlers = {
            **self._system_tools.handlers(),
            **self._process_tools.handlers(cancellation),
        }
        result_keys = {
            "system.os": "operating_system",
            "system.cpu": "cpu",
            "system.gpu": "gpus",
            "system.memory": "memory",
            "system.disks": "disks",
            "process.snapshot": "processes",
            "process.high_usage": "high_usage_processes",
        }
        summary: dict[str, object] = {
            "capabilities": _serialize(self._system_tools.capabilities()),
        }
        failures: list[dict[str, str]] = []
        ordered_names = [spec.name for spec in (*SYSTEM_TOOL_SPECS, *PROCESS_TOOL_SPECS)]
        self._repository.update(
            scan_id, status="running", progress=0, current_step=ordered_names[0]
        )
        log_event(
            _LOGGER,
            logging.INFO,
            "Quick scan started.",
            component="quick_scan",
            event_type="scan_started",
            correlation_id=correlation_id,
            scan_id=scan_id,
        )

        for index, name in enumerate(ordered_names):
            if cancellation.is_set():
                self._finish_cancelled(scan_id, summary, failures)
                return
            spec = specs[name]
            self._repository.update(
                scan_id,
                status="running",
                progress=round(index / len(ordered_names) * 100),
                current_step=name,
            )
            started_at = _now()
            started = time.monotonic()
            step_status: StepStatus = "completed"
            error_code: str | None = None
            error_message: str | None = None
            result_summary: dict[str, object] | None = None
            try:
                value = await asyncio.wait_for(
                    asyncio.to_thread(handlers[name]), timeout=spec.timeout_seconds
                )
                summary[result_keys[name]] = _serialize(value)
                result_summary = _result_summary(value)
            except Exception as error:
                error_code, error_message, step_status = _failure(error)
                failures.append({"tool": name, "code": error_code, "message": error_message})
            finished_at = _now()
            self._record_event(
                scan_id=scan_id,
                spec=spec,
                status=step_status,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=round((time.monotonic() - started) * 1000),
                result_summary=result_summary,
                error_code=error_code,
                error_message=error_message,
            )
            if step_status == "cancelled" or cancellation.is_set():
                self._finish_cancelled(scan_id, summary, failures)
                return

        final_status: Literal["partial", "completed"] = "partial" if failures else "completed"
        self._repository.update(
            scan_id,
            status=final_status,
            progress=100,
            current_step=None,
            finished_at=_now(),
            summary=summary,
            failures=failures,
        )
        self._cancellations.pop(scan_id, None)
        log_event(
            _LOGGER,
            logging.INFO,
            "Quick scan finished.",
            component="quick_scan",
            event_type="scan_finished",
            correlation_id=correlation_id,
            scan_id=scan_id,
            status=final_status,
            failed_step_count=len(failures),
        )

    async def _run_guarded(
        self,
        scan_id: str,
        cancellation: Event,
        correlation_id: str | None,
    ) -> None:
        try:
            async with asyncio.timeout(30):
                await self._run(scan_id, cancellation, correlation_id)
        except asyncio.CancelledError:
            record = self._repository.get(scan_id)
            if record and record.status in {"queued", "running"}:
                self._finish_cancelled(scan_id, record.summary or {}, record.failures)
        except TimeoutError:
            cancellation.set()
            record = self._repository.get(scan_id)
            if record and record.status in {"queued", "running"}:
                self._repository.update(
                    scan_id,
                    status="failed",
                    progress=record.progress,
                    current_step=None,
                    finished_at=_now(),
                    summary=record.summary or {},
                    failures=[
                        *record.failures,
                        {
                            "tool": "quick_scan",
                            "code": "global_timeout",
                            "message": "快速扫描达到 30 秒总预算，底层操作正在有界收尾。",
                        },
                    ],
                )
        except Exception as error:
            record = self._repository.get(scan_id)
            if record and record.status in {"queued", "running"}:
                failures = [
                    *record.failures,
                    {
                        "tool": record.current_step or "scan",
                        "code": "scan_failed",
                        "message": "扫描任务意外中断。",
                    },
                ]
                self._repository.update(
                    scan_id,
                    status="failed",
                    progress=record.progress,
                    current_step=None,
                    finished_at=_now(),
                    summary=record.summary or {},
                    failures=failures,
                )
            log_event(
                _LOGGER,
                logging.ERROR,
                "Quick scan failed unexpectedly.",
                component="quick_scan",
                event_type="scan_failed",
                correlation_id=correlation_id,
                scan_id=scan_id,
                error_type=type(error).__name__,
            )
        finally:
            self._cancellations.pop(scan_id, None)

    def _finish_cancelled(
        self,
        scan_id: str,
        summary: dict[str, object],
        failures: Sequence[dict[str, str]],
    ) -> None:
        current = self._repository.get(scan_id)
        self._repository.update(
            scan_id,
            status="cancelled",
            progress=current.progress if current else 0,
            current_step=None,
            finished_at=_now(),
            summary=summary,
            failures=failures,
        )
        self._cancellations.pop(scan_id, None)

    def _record_event(
        self,
        *,
        scan_id: str,
        spec: ToolSpec,
        status: StepStatus,
        started_at: str,
        finished_at: str,
        duration_ms: int,
        result_summary: dict[str, object] | None,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        self._repository.add_step_event(
            scan_id=scan_id,
            tool_name=spec.name,
            tool_version=spec.version,
            arguments_hash=NO_ARGUMENTS_HASH,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            result_summary=result_summary,
            error_code=error_code,
            error_message=error_message,
        )
