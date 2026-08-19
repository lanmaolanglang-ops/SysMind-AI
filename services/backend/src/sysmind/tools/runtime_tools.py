from __future__ import annotations

from dataclasses import asdict
from threading import Event
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from sysmind.application.ports.diagnostics import ProcessProbe, SystemProbe
from sysmind.application.ports.event_logs import EventLogProbe
from sysmind.application.ports.platform_inspection import NetworkProbe, ServiceProbe, StartupProbe
from sysmind.domain.diagnostics import (
    CpuInfo,
    DiskStatus,
    GpuInfo,
    MemoryStatus,
    OperatingSystemInfo,
    ProcessInfo,
)
from sysmind.domain.event_logs import EventLevel, EventLogQuery, WindowsEvent
from sysmind.tools.platform_tools import platform_tool_definitions
from sysmind.tools.registry import ToolDefinition, ToolHandler, ToolRegistry


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcessSnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=100, ge=1, le=200)


class HighUsageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_seconds: float = Field(default=0.5, ge=0.1, le=2.0)
    cpu_threshold: float = Field(default=25.0, ge=1, le=100)
    memory_threshold: float = Field(default=10.0, ge=1, le=100)
    limit: int = Field(default=20, ge=1, le=50)


class EventLogToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["Application", "System"]
    lookback_hours: int = Field(ge=1, le=168)
    levels: tuple[EventLevel, ...] = Field(min_length=1, max_length=4)
    event_ids: tuple[int, ...] = Field(default=(), max_length=32)
    max_events: int = Field(default=50, ge=1, le=200)

    @field_validator("levels", "event_ids")
    @classmethod
    def unique_values(cls, value: tuple[object, ...]) -> tuple[object, ...]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate filters are not allowed")
        return value

    @field_validator("event_ids")
    @classmethod
    def bounded_event_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item < 0 or item > 65535 for item in value):
            raise ValueError("event IDs must be between 0 and 65535")
        return value


def _object_summary(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _list_summary(value: object) -> dict[str, object]:
    items = cast(list[object], value)
    return {"item_count": len(items), "items": items[:10]}


def _event_summary(value: object) -> dict[str, object]:
    items = cast(list[dict[str, object]], value)
    safe_items = [
        {
            key: item.get(key)
            for key in (
                "channel",
                "provider",
                "event_id",
                "level",
                "timestamp",
                "application",
                "faulting_module",
                "exception_code",
            )
        }
        for item in items[:10]
    ]
    return {"item_count": len(items), "items": safe_items}


def build_runtime_registry(
    system_probe: SystemProbe,
    process_probe: ProcessProbe,
    event_log_probe: EventLogProbe,
    network_probe: NetworkProbe | None = None,
    startup_probe: StartupProbe | None = None,
    service_probe: ServiceProbe | None = None,
) -> ToolRegistry:
    def system_handler(method_name: str) -> ToolHandler:
        def handler(_input: BaseModel, _cancel: Event) -> object:
            return getattr(system_probe, method_name)()

        return handler

    def snapshot(input_model: BaseModel, _cancel: Event) -> object:
        parameters = cast(ProcessSnapshotInput, input_model)
        return process_probe.snapshot(limit=parameters.limit)

    def high_usage(input_model: BaseModel, cancel: Event) -> object:
        parameters = cast(HighUsageInput, input_model)
        return process_probe.high_usage(
            cancel,
            sample_seconds=parameters.sample_seconds,
            cpu_threshold=parameters.cpu_threshold,
            memory_threshold=parameters.memory_threshold,
            limit=parameters.limit,
        )

    def event_query(input_model: BaseModel, cancel: Event) -> object:
        parameters = cast(EventLogToolInput, input_model)
        return event_log_probe.query(
            EventLogQuery(
                channel=parameters.channel,
                lookback_hours=parameters.lookback_hours,
                levels=parameters.levels,
                event_ids=parameters.event_ids,
                max_events=parameters.max_events,
            ),
            cancel,
        )

    def crash_analysis(input_model: BaseModel, cancel: Event) -> object:
        parameters = cast(EventLogToolInput, input_model)
        events = event_log_probe.query(
            EventLogQuery(
                channel="Application",
                lookback_hours=parameters.lookback_hours,
                levels=parameters.levels,
                event_ids=parameters.event_ids or (1000, 1001),
                max_events=parameters.max_events,
            ),
            cancel,
        )
        groups: dict[tuple[str, str, str], dict[str, object]] = {}
        for event in events:
            key = (
                event.application or "unknown",
                event.faulting_module or "unknown",
                event.exception_code or "unknown",
            )
            group = groups.setdefault(
                key,
                {
                    "application": key[0],
                    "faulting_module": key[1],
                    "exception_code": key[2],
                    "count": 0,
                    "latest_event": asdict(event),
                },
            )
            group["count"] = cast(int, group["count"]) + 1
        return tuple(groups.values())

    definitions = (
        ToolDefinition(
            "system.os",
            "1.0",
            "Read normalized Windows version metadata. Never changes the system.",
            EmptyInput,
            TypeAdapter(OperatingSystemInfo),
            "read_only",
            "user",
            (),
            3.0,
            "system",
            "none",
            system_handler("operating_system"),
            _object_summary,
        ),
        ToolDefinition(
            "system.cpu",
            "1.0",
            "Read CPU topology and a bounded utilization sample. Never controls processes.",
            EmptyInput,
            TypeAdapter(CpuInfo),
            "read_only",
            "user",
            (),
            3.0,
            "system",
            "none",
            system_handler("cpu"),
            _object_summary,
        ),
        ToolDefinition(
            "system.gpu",
            "1.0",
            "Read normalized GPU metadata using the fixed application collector.",
            EmptyInput,
            TypeAdapter(tuple[GpuInfo, ...]),
            "read_only",
            "user",
            (),
            8.0,
            "system",
            "none",
            system_handler("gpus"),
            _list_summary,
        ),
        ToolDefinition(
            "system.memory",
            "1.0",
            "Read current memory capacity and utilization. Never changes memory state.",
            EmptyInput,
            TypeAdapter(MemoryStatus),
            "read_only",
            "user",
            (),
            3.0,
            "system",
            "none",
            system_handler("memory"),
            _object_summary,
        ),
        ToolDefinition(
            "system.disks",
            "1.0",
            "Read bounded mounted-volume capacity. Never reads file contents or deletes files.",
            EmptyInput,
            TypeAdapter(tuple[DiskStatus, ...]),
            "read_only",
            "user",
            ("path",),
            5.0,
            "system",
            "none",
            system_handler("disks"),
            _list_summary,
        ),
        ToolDefinition(
            "process.snapshot",
            "1.0",
            "Read a bounded process resource snapshot. Cannot terminate or modify a process.",
            ProcessSnapshotInput,
            TypeAdapter(tuple[ProcessInfo, ...]),
            "read_only",
            "user",
            ("process",),
            8.0,
            "process",
            "none",
            snapshot,
            _list_summary,
        ),
        ToolDefinition(
            "process.high_usage",
            "1.0",
            "Sample high CPU or memory usage for at most two seconds. Cannot terminate processes.",
            HighUsageInput,
            TypeAdapter(tuple[ProcessInfo, ...]),
            "read_only",
            "user",
            ("process",),
            8.0,
            "process",
            "none",
            high_usage,
            _list_summary,
        ),
        ToolDefinition(
            "log.windows_event.query",
            "1.0",
            "Read bounded, allowlisted Application or System event summaries; never raw XML.",
            EventLogToolInput,
            TypeAdapter(tuple[WindowsEvent, ...]),
            "read_only",
            "user",
            ("event_log", "identity", "path", "ip"),
            12.0,
            "event_log",
            "none",
            event_query,
            _event_summary,
        ),
        ToolDefinition(
            "log.crash.analyze",
            "1.0",
            "Aggregate bounded Application Error and WER summaries; never reads crash dumps.",
            EventLogToolInput,
            TypeAdapter(tuple[dict[str, object], ...]),
            "read_only",
            "user",
            ("event_log", "identity", "path"),
            12.0,
            "event_log",
            "none",
            crash_analysis,
            _list_summary,
        ),
    )
    return ToolRegistry(
        definitions + platform_tool_definitions(network_probe, startup_probe, service_probe)
    )
