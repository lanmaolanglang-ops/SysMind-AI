from __future__ import annotations

import json
import platform
import shutil
import subprocess
from collections.abc import Sequence
from threading import Event
from typing import Any

import psutil

from sysmind.domain.diagnostics import (
    Capability,
    CpuInfo,
    DiskStatus,
    GpuInfo,
    MemoryStatus,
    OperatingSystemInfo,
    ProcessInfo,
)
from sysmind.tools.contracts import ToolCancelledError, ToolUnavailableError

_GPU_COMMAND = (
    "Get-CimInstance Win32_VideoController | "
    "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress"
)


def _normalized_cpu_percent(raw_percent: float, logical_cores: int | None = None) -> float:
    cores = logical_cores or psutil.cpu_count(logical=True) or 1
    return round(min(max(raw_percent / cores, 0.0), 100.0), 1)


def _cpu_model() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            if isinstance(value, str) and value.strip():
                return value.strip()
    except (ImportError, OSError):
        pass
    return platform.processor().strip() or "Unknown processor"


class WindowsSystemProbe:
    def __init__(self, powershell_path: str | None = None) -> None:
        self._powershell_path = powershell_path or shutil.which("powershell")

    def capabilities(self) -> Sequence[Capability]:
        return (
            Capability("system.os", True),
            Capability("system.cpu", True),
            Capability("system.memory", True),
            Capability("system.disks", True),
            Capability(
                "system.gpu",
                self._powershell_path is not None,
                None if self._powershell_path else "Windows PowerShell is unavailable.",
            ),
        )

    def operating_system(self) -> OperatingSystemInfo:
        return OperatingSystemInfo(
            name=platform.system() or "Windows",
            version=platform.version(),
            build=platform.release(),
            architecture=platform.machine(),
        )

    def cpu(self) -> CpuInfo:
        frequency = psutil.cpu_freq()
        return CpuInfo(
            model=_cpu_model(),
            physical_cores=psutil.cpu_count(logical=False) or 0,
            logical_cores=psutil.cpu_count(logical=True) or 0,
            utilization_percent=round(psutil.cpu_percent(interval=0.15), 1),
            frequency_mhz=round(frequency.current, 1) if frequency else None,
        )

    def gpus(self) -> Sequence[GpuInfo]:
        if self._powershell_path is None:
            raise ToolUnavailableError("GPU collection requires Windows PowerShell.")
        completed = subprocess.run(
            [self._powershell_path, "-NoProfile", "-NonInteractive", "-Command", _GPU_COMMAND],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            raise ToolUnavailableError("Windows did not return GPU information.")
        raw = completed.stdout.strip()
        if not raw:
            return ()
        payload: Any = json.loads(raw)
        rows = payload if isinstance(payload, list) else [payload]
        return tuple(
            GpuInfo(
                name=str(row.get("Name") or "Unknown GPU"),
                memory_bytes=int(row["AdapterRAM"]) if row.get("AdapterRAM") is not None else None,
                driver_version=(str(row["DriverVersion"]) if row.get("DriverVersion") else None),
            )
            for row in rows
            if isinstance(row, dict)
        )

    def memory(self) -> MemoryStatus:
        value = psutil.virtual_memory()
        return MemoryStatus(
            total_bytes=value.total,
            available_bytes=value.available,
            used_bytes=value.used,
            utilization_percent=round(value.percent, 1),
        )

    def disks(self) -> Sequence[DiskStatus]:
        results: list[DiskStatus] = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (OSError, PermissionError):
                continue
            results.append(
                DiskStatus(
                    volume=partition.device,
                    mountpoint=partition.mountpoint,
                    filesystem=partition.fstype,
                    total_bytes=usage.total,
                    free_bytes=usage.free,
                    used_bytes=usage.used,
                    utilization_percent=round(usage.percent, 1),
                )
            )
        return tuple(results)


class WindowsProcessProbe:
    @staticmethod
    def _read_process(process: psutil.Process) -> ProcessInfo | None:
        try:
            memory = process.memory_info()
            return ProcessInfo(
                pid=process.pid,
                name=process.name(),
                cpu_percent=_normalized_cpu_percent(process.cpu_percent(interval=None)),
                memory_bytes=memory.rss,
                memory_percent=round(process.memory_percent(), 2),
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            return None

    def snapshot(self, limit: int = 200) -> Sequence[ProcessInfo]:
        items = [item for process in psutil.process_iter() if (item := self._read_process(process))]
        items.sort(key=lambda item: (item.memory_bytes, item.cpu_percent), reverse=True)
        return tuple(items[:limit])

    def high_usage(
        self,
        cancel_event: Event,
        *,
        sample_seconds: float = 0.5,
        cpu_threshold: float = 25.0,
        memory_threshold: float = 10.0,
        limit: int = 20,
    ) -> Sequence[ProcessInfo]:
        processes = list(psutil.process_iter())
        for process in processes:
            try:
                process.cpu_percent(interval=None)
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
        if cancel_event.wait(sample_seconds):
            raise ToolCancelledError("Process sampling was cancelled.")
        items = [item for process in processes if (item := self._read_process(process))]
        matches = [
            item
            for item in items
            if item.pid != 0
            and item.name.casefold() != "system idle process"
            and (item.cpu_percent >= cpu_threshold or item.memory_percent >= memory_threshold)
        ]
        matches.sort(key=lambda item: (item.cpu_percent, item.memory_bytes), reverse=True)
        return tuple(matches[:limit])
