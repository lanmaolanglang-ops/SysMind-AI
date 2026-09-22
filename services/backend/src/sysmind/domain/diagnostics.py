from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, TypeAlias


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


# Neutral, adapter-agnostic copy shown whenever real-time GPU telemetry is unavailable.
GPU_TELEMETRY_UNAVAILABLE = "Real-time GPU utilization is unavailable."
# WDDM counters expose a per-adapter LUID, and Win32_VideoController does not, so the
# readings cannot be attributed to a named adapter on multi-GPU systems.
GpuTelemetryScope: TypeAlias = Literal["system", "adapter"]
GPU_TELEMETRY_SYSTEM_SCOPE: Final[GpuTelemetryScope] = "system"
GPU_TELEMETRY_ADAPTER_SCOPE: Final[GpuTelemetryScope] = "adapter"
GPU_TELEMETRY_UNAVAILABLE_OTHERS = (
    "GPU telemetry is reported at system level and attached to the first adapter."
)


@dataclass(frozen=True, slots=True)
class GpuInfo:
    name: str
    memory_bytes: int | None
    driver_version: str | None
    telemetry_available: bool = False
    utilization_percent: float | None = None
    memory_used_bytes: int | None = None
    telemetry_limitation: str | None = None
    telemetry_scope: GpuTelemetryScope = GPU_TELEMETRY_ADAPTER_SCOPE

    def __post_init__(self) -> None:
        if self.telemetry_available:
            if self.telemetry_limitation is not None:
                raise ValueError("Available GPU telemetry cannot also declare a limitation.")
            return
        # Unavailable telemetry always carries an explanation, so consumers never have to
        # guess why utilization is missing.
        if self.telemetry_limitation is None:
            object.__setattr__(self, "telemetry_limitation", GPU_TELEMETRY_UNAVAILABLE)


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
    item_id: str | None = None


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
    failures: tuple[dict[str, str], ...]
    schema_version: str

    def __post_init__(self) -> None:
        if not 0 <= self.progress <= 100:
            raise ValueError(f"progress must be between 0 and 100, got {self.progress}.")
        # `frozen=True` blocks attribute rebinding but not mutation of the containers, so
        # the mapping is copied to stop an external reference from mutating the record.
        if self.summary is not None:
            object.__setattr__(self, "summary", dict(self.summary))
