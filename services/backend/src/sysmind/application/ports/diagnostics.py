from __future__ import annotations

from collections.abc import Sequence
from threading import Event
from typing import Protocol

from sysmind.domain.diagnostics import (
    Capability,
    CpuInfo,
    DiskStatus,
    GpuInfo,
    MemoryStatus,
    OperatingSystemInfo,
    ProcessInfo,
)


class SystemProbe(Protocol):
    def capabilities(self) -> Sequence[Capability]: ...

    def operating_system(self) -> OperatingSystemInfo: ...

    def cpu(self) -> CpuInfo: ...

    def gpus(self) -> Sequence[GpuInfo]: ...

    def memory(self) -> MemoryStatus: ...

    def disks(self) -> Sequence[DiskStatus]: ...


class ProcessProbe(Protocol):
    def snapshot(self, limit: int = 200) -> Sequence[ProcessInfo]: ...

    def high_usage(
        self,
        cancel_event: Event,
        *,
        sample_seconds: float = 0.5,
        cpu_threshold: float = 25.0,
        memory_threshold: float = 10.0,
        limit: int = 20,
    ) -> Sequence[ProcessInfo]: ...

