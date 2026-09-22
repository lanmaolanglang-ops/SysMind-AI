from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from threading import Event
from typing import cast, get_args

from sysmind.application.ports.log_analyses import LogAnalysisRepository
from sysmind.application.ports.state_conflict import StateConflict
from sysmind.domain.diagnostics import StepStatus
from sysmind.domain.event_logs import (
    MAX_EVENTS,
    MAX_LOOKBACK_HOURS,
    AnalysisStatus,
    EventLevel,
    EventLogQuery,
    LogAnalysisRecord,
    LogChannel,
    WindowsEvent,
)
from sysmind.observability.logging import log_event
from sysmind.tools.contracts import (
    ToolCancelledError,
    ToolPermissionError,
    ToolSpec,
    ToolUnavailableError,
)
from sysmind.tools.executor import AnyCancelEvent
from sysmind.tools.log import LOG_TOOL_SPECS, LogTools

LOG_ANALYSIS_SCHEMA_VERSION = "1.0"
_LOGGER = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


# Kept in step with QuickScanCoordinator: a crash used to strand a running
# analysis until the user started a new one. Only recently started work is
# replayed, and only a little of it, so a backlog cannot flood the machine.
# Allowlist constants used when validating a stored query (kept for any future
# opt-in resume path and for defense-in-depth tests).
_ALLOWED_CHANNEL_NAMES = frozenset(get_args(LogChannel))
_ALLOWED_LEVEL_NAMES = frozenset(get_args(EventLevel))


def _replay_parameters(
    query: dict[str, object],
) -> tuple[tuple[LogChannel, ...], int, tuple[EventLevel, ...], tuple[int, ...], int] | None:
    """Rebuild the original request from the stored query, or refuse to guess."""
    channels = query.get("channels")
    lookback_hours = query.get("lookback_hours")
    levels = query.get("levels")
    event_ids = query.get("event_ids")
    max_events = query.get("max_events")
    if not isinstance(channels, list) or not channels:
        return None
    if not isinstance(levels, list) or not levels:
        return None
    if not isinstance(event_ids, list):
        return None
    if not isinstance(lookback_hours, int) or not 1 <= lookback_hours <= MAX_LOOKBACK_HOURS:
        return None
    if not isinstance(max_events, int) or not 1 <= max_events <= MAX_EVENTS:
        return None
    if not all(item in _ALLOWED_CHANNEL_NAMES for item in channels):
        return None
    if not all(item in _ALLOWED_LEVEL_NAMES for item in levels):
        return None
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in event_ids):
        return None
    return (
        cast("tuple[LogChannel, ...]", tuple(str(item) for item in channels)),
        lookback_hours,
        cast("tuple[EventLevel, ...]", tuple(str(item) for item in levels)),
        tuple(int(item) for item in event_ids),
        max_events,
    )


def _arguments_hash(arguments: dict[str, object]) -> str:
    encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _failure(error: Exception) -> tuple[str, str, StepStatus]:
    if isinstance(error, TimeoutError):
        return "tool_timeout", "日志查询超时，已跳过该通道。", "timed_out"
    if isinstance(error, ToolPermissionError):
        return "permission_required", str(error), "failed"
    if isinstance(error, ToolUnavailableError):
        return "capability_unavailable", str(error), "failed"
    if isinstance(error, ToolCancelledError):
        return "analysis_cancelled", "日志分析已取消。", "cancelled"
    if isinstance(error, ValueError):
        return "invalid_query", "日志查询参数不符合安全范围。", "failed"
    return "collection_failed", "该日志通道暂时无法读取。", "failed"


class LogAnalysisCoordinator:
    def __init__(self, repository: LogAnalysisRepository, tools: LogTools) -> None:
        self._repository = repository
        self._tools = tools
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._cancellations: dict[str, Event] = {}

    def start(
        self,
        *,
        channels: tuple[LogChannel, ...],
        lookback_hours: int,
        levels: tuple[EventLevel, ...],
        event_ids: tuple[int, ...],
        max_events: int,
        correlation_id: str | None = None,
    ) -> LogAnalysisRecord:
        if not channels:
            # Fail before persisting anything: an empty channel list would otherwise blow up
            # inside the background task as an opaque IndexError.
            raise ValueError("At least one event-log channel must be requested.")
        query: dict[str, object] = {
            "channels": list(channels),
            "lookback_hours": lookback_hours,
            "levels": list(levels),
            "event_ids": list(event_ids),
            "max_events": max_events,
        }
        analysis_id = str(uuid.uuid4())
        record = self._repository.create(analysis_id, _now(), query, LOG_ANALYSIS_SCHEMA_VERSION)
        cancellation = Event()
        self._cancellations[analysis_id] = cancellation
        task = asyncio.create_task(
            self._run_guarded(
                analysis_id,
                channels,
                lookback_hours,
                levels,
                event_ids,
                max_events,
                cancellation,
                correlation_id,
            ),
            name=f"log-analysis-{analysis_id}",
        )
        self._tasks[analysis_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(analysis_id, None))
        return record

    def get(self, analysis_id: str) -> LogAnalysisRecord | None:
        return self._repository.get(analysis_id)

    def recent(self, limit: int = 20) -> list[LogAnalysisRecord]:
        return self._repository.recent(limit)

    def recover_interrupted(self) -> int:
        """Mark orphaned analyses as failed; do not auto-replay.

        PRD/ADR require that an interrupted run terminates rather than silently
        restarting collection. Users can start a new analysis from the UI.
        """
        return self._repository.mark_interrupted(_now())

    def cancel(self, analysis_id: str) -> LogAnalysisRecord | None:
        record = self._repository.get(analysis_id)
        if record is None:
            return None
        cancellation = self._cancellations.get(analysis_id)
        if cancellation and record.status in {"queued", "running"}:
            cancellation.set()
        return record

    async def shutdown(self) -> None:
        for cancellation in self._cancellations.values():
            cancellation.set()
        if self._tasks:
            _, pending = await asyncio.wait(tuple(self._tasks.values()), timeout=2.5)
            for task in pending:
                task.cancel()

    async def _run(
        self,
        analysis_id: str,
        channels: tuple[LogChannel, ...],
        lookback_hours: int,
        levels: tuple[EventLevel, ...],
        event_ids: tuple[int, ...],
        max_events: int,
        cancellation: Event,
        correlation_id: str | None,
        collected_events: list[WindowsEvent],
    ) -> None:
        failures: list[dict[str, str]] = []
        events = collected_events
        specs_by_name = {spec.name: spec for spec in LOG_TOOL_SPECS}
        query_spec = specs_by_name["log.windows_event.query"]
        analyze_spec = specs_by_name["log.crash.analyze"]
        steps = len(channels) + 1
        self._repository.update(
            analysis_id,
            status="running",
            progress=0,
            current_step=f"{query_spec.name}:{channels[0]}",
        )
        log_event(
            _LOGGER,
            logging.INFO,
            "Event log analysis started.",
            component="log_analysis",
            event_type="analysis_started",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
        )

        for index, channel_value in enumerate(channels):
            if cancellation.is_set():
                self._finish_cancelled(analysis_id, events, failures, max_events=max_events)
                return
            channel = channel_value
            event_query = EventLogQuery(
                channel=channel,
                lookback_hours=lookback_hours,
                levels=levels,
                event_ids=event_ids,
                max_events=max_events,
            )
            current_step = f"{query_spec.name}:{channel}"
            self._repository.update(
                analysis_id,
                status="running",
                progress=round(index / steps * 100),
                current_step=current_step,
            )
            try:
                result = await self._execute_query(
                    analysis_id, query_spec, event_query, cancellation
                )
                events.extend(result)
            except Exception as error:
                code, message, failure_status = _failure(error)
                failures.append({"tool": current_step, "code": code, "message": message})
                if failure_status == "cancelled":
                    self._finish_cancelled(
                        analysis_id, events, failures, max_events=max_events
                    )
                    return

        if cancellation.is_set():
            self._finish_cancelled(analysis_id, events, failures, max_events=max_events)
            return
        typed_events = sorted(events, key=lambda item: item.timestamp, reverse=True)[:max_events]
        self._repository.update(
            analysis_id,
            status="running",
            progress=round((steps - 1) / steps * 100),
            current_step=analyze_spec.name,
        )
        started_at = _now()
        started = time.monotonic()
        crash_groups = self._tools.analyze(typed_events)
        event_groups = self._tools.aggregate(typed_events)
        finished_at = _now()
        self._repository.add_step_event(
            analysis_id=analysis_id,
            tool_name=analyze_spec.name,
            tool_version=analyze_spec.version,
            status="completed",
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=round((time.monotonic() - started) * 1000),
            arguments_hash=_arguments_hash({"event_count": len(typed_events)}),
            result_summary={
                "event_group_count": len(event_groups),
                "crash_group_count": len(crash_groups),
            },
        )
        summary: dict[str, object] = {
            "event_count": len(typed_events),
            "events": [asdict(item) for item in typed_events],
            "event_groups": [asdict(item) for item in event_groups],
            "crash_groups": [asdict(item) for item in crash_groups],
            "notice": "结果已在本地归一化并脱敏；未保存原始事件 XML。",
        }
        final_status: AnalysisStatus = "partial" if failures else "completed"
        if failures and not typed_events:
            final_status = "failed"
        try:
            self._repository.update(
                analysis_id,
                status=final_status,
                progress=100,
                current_step=None,
                finished_at=_now(),
                summary=summary,
                failures=failures,
                expected_statuses=("queued", "running"),
            )
        except StateConflict:
            log_event(
                _LOGGER,
                logging.INFO,
                "Log analysis finalize lost the terminal-state race.",
                component="log_analysis",
                event_type="analysis_state_conflict",
                correlation_id=correlation_id,
                analysis_id=analysis_id,
                requested_status=final_status,
            )
            return
        log_event(
            _LOGGER,
            logging.INFO,
            "Event log analysis finished.",
            component="log_analysis",
            event_type="analysis_finished",
            correlation_id=correlation_id,
            analysis_id=analysis_id,
            status=final_status,
            event_count=len(typed_events),
            failed_step_count=len(failures),
        )

    async def _execute_query(
        self,
        analysis_id: str,
        spec: ToolSpec,
        query: EventLogQuery,
        cancellation: Event,
    ) -> tuple[WindowsEvent, ...]:
        started_at = _now()
        started = time.monotonic()
        status: StepStatus = "completed"
        error_code: str | None = None
        error_message: str | None = None
        result: tuple[WindowsEvent, ...] = ()
        arguments = asdict(query)
        timed_out = Event()
        try:
            value = await asyncio.wait_for(
                asyncio.to_thread(
                    self._tools.query, query, AnyCancelEvent(cancellation, timed_out)
                ),
                timeout=spec.timeout_seconds,
            )
            result = tuple(value)
            return result
        except Exception as error:
            if isinstance(error, TimeoutError):
                # wait_for abandons the awaitable but the worker thread keeps running;
                # signal just this query so it can stop without cancelling siblings.
                timed_out.set()
            error_code, error_message, status = _failure(error)
            raise
        finally:
            self._repository.add_step_event(
                analysis_id=analysis_id,
                tool_name=spec.name,
                tool_version=spec.version,
                status=status,
                started_at=started_at,
                finished_at=_now(),
                duration_ms=round((time.monotonic() - started) * 1000),
                arguments_hash=_arguments_hash(arguments),
                result_summary={"channel": query.channel, "item_count": len(result)},
                error_code=error_code,
                error_message=error_message,
            )

    async def _run_guarded(
        self,
        analysis_id: str,
        channels: tuple[LogChannel, ...],
        lookback_hours: int,
        levels: tuple[EventLevel, ...],
        event_ids: tuple[int, ...],
        max_events: int,
        cancellation: Event,
        correlation_id: str | None,
    ) -> None:
        # Shared with _run so a CancelledError can still persist what was collected.
        collected_events: list[WindowsEvent] = []
        try:
            async with asyncio.timeout(30):
                await self._run(
                    analysis_id,
                    channels,
                    lookback_hours,
                    levels,
                    event_ids,
                    max_events,
                    cancellation,
                    correlation_id,
                    collected_events,
                )
        except asyncio.CancelledError:
            record = self._repository.get(analysis_id)
            if record and record.status in {"queued", "running"}:
                self._finish_cancelled(
                    analysis_id, collected_events, record.failures, max_events=max_events
                )
        except TimeoutError:
            cancellation.set()
            record = self._repository.get(analysis_id)
            if record and record.status in {"queued", "running"}:
                with contextlib.suppress(StateConflict):
                    self._repository.update(
                        analysis_id,
                        status="failed",
                        progress=record.progress,
                        current_step=None,
                        finished_at=_now(),
                        summary=record.summary or {},
                        failures=[
                            *record.failures,
                            {
                                "tool": "log_analysis",
                                "code": "global_timeout",
                                "message": "日志分析达到 30 秒总预算，底层操作正在有界收尾。",
                            },
                        ],
                        expected_statuses=("queued", "running"),
                    )
        except Exception as error:
            record = self._repository.get(analysis_id)
            if record and record.status in {"queued", "running"}:
                with contextlib.suppress(StateConflict):
                    self._repository.update(
                        analysis_id,
                        status="failed",
                        progress=record.progress,
                        current_step=None,
                        finished_at=_now(),
                        summary=record.summary or {},
                        failures=[
                            *record.failures,
                            {
                                "tool": record.current_step or "log_analysis",
                                "code": "analysis_failed",
                                "message": "日志分析任务意外中断。",
                            },
                        ],
                        expected_statuses=("queued", "running"),
                    )
            log_event(
                _LOGGER,
                logging.ERROR,
                "Event log analysis failed unexpectedly.",
                component="log_analysis",
                event_type="analysis_failed",
                correlation_id=correlation_id,
                analysis_id=analysis_id,
                error_type=type(error).__name__,
            )
        finally:
            self._cancellations.pop(analysis_id, None)

    def _finish_cancelled(
        self,
        analysis_id: str,
        events: list[WindowsEvent],
        failures: Sequence[dict[str, str]],
        *,
        max_events: int,
    ) -> None:
        current = self._repository.get(analysis_id)
        retained_events = sorted(events, key=lambda item: item.timestamp, reverse=True)[
            :max_events
        ]
        with contextlib.suppress(StateConflict):
            self._repository.update(
                analysis_id,
                status="cancelled",
                progress=current.progress if current else 0,
                current_step=None,
                finished_at=_now(),
                summary={
                    "event_count": len(retained_events),
                    "events": [asdict(item) for item in retained_events],
                    "event_groups": [],
                    "crash_groups": [],
                    "notice": "分析已取消；仅保留取消前在本地归一化并脱敏的事件。",
                },
                failures=failures,
                expected_statuses=("queued", "running"),
            )
