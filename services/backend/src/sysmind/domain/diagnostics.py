from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    available: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OperatingSystemInfo:
    name: str
    version: str
    build: str
    architecture: str


@dataclass(frozen=True, slots=True)
class CpuInfo:
    model: str
    physical_cores: int
    logical_cores: int
    utilization_percent: float
    frequency_mhz: float | None


@dataclass(frozen=True, slots=True)
class GpuInfo:
    name: str
    memory_bytes: int | None
    driver_version: str | None


@dataclass(frozen=True, slots=True)
class MemoryStatus:
    total_bytes: int
    available_bytes: int
    used_bytes: int
    utilization_percent: float


@dataclass(frozen=True, slots=True)
class DiskStatus:
    volume: str
    mountpoint: str
    filesystem: str
    total_bytes: int
    free_bytes: int
    used_bytes: int
    utilization_percent: float


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_bytes: int
    memory_percent: float


ScanStatus = Literal["queued", "running", "completed", "partial", "cancelled", "failed"]
StepStatus = Literal["running", "completed", "failed", "cancelled", "timed_out"]


@dataclass(frozen=True, slots=True)
class ScanRecord:
    id: str
    status: ScanStatus
    progress: int
    current_step: str | None
    started_at: str
    finished_at: str | None
    summary: dict[str, object] | None
    failures: list[dict[str, str]]
    schema_version: str
