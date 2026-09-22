from __future__ import annotations

import json
import platform
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import replace
from threading import Event
from typing import Any

import psutil

from sysmind.domain.diagnostics import (
    GPU_TELEMETRY_SYSTEM_SCOPE,
    GPU_TELEMETRY_UNAVAILABLE_OTHERS,
    Capability,
    CpuInfo,
    DiskStatus,
    GpuInfo,
    MemoryStatus,
    OperatingSystemInfo,
    ProcessInfo,
)
from sysmind.tools.contracts import ToolCancelledError, ToolUnavailableError
from sysmind.windows.identity import process_item_id

# Windows PowerShell 5.1 emits the console code page (cp936 on Chinese Windows),
# so forcing Python to decode UTF-8 is not enough — the child must also write UTF-8
# or GPU names containing non-ASCII characters arrive as mojibake.
_POWERSHELL_UTF8_PREAMBLE = (
    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false);"
    "$OutputEncoding = [Console]::OutputEncoding;"
)

_GPU_COMMAND = _POWERSHELL_UTF8_PREAMBLE + (
    "Get-CimInstance Win32_VideoController | "
    "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress"
)

# Samples the WDDM GPU counters once. `-MaxSamples 1` still costs one sample
# interval (~1s), which is why this is a separate, individually timed call rather
# than being folded into the metadata query above.
_GPU_TELEMETRY_COMMAND = _POWERSHELL_UTF8_PREAMBLE + (
    "$s = Get-Counter -Counter '\\GPU Engine(*)\\Utilization Percentage',"
    "'\\GPU Adapter Memory(*)\\Dedicated Usage' -MaxSamples 1 -ErrorAction Stop;"
    "@($s.CounterSamples) | ForEach-Object {"
    " $i = [string]$_.InstanceName;"
    " if ($i -match 'luid_[0-9a-fA-Fx_]+_phys_[0-9]+') {"
    "  $a = $Matches[0];"
    "  if ($i -match 'engtype_([a-z0-9]+)') {"
    "   [pscustomobject]@{a = ($a + '|' + $Matches[1]); t = 'e';"
    "                    v = [math]::Round([double]$_.CookedValue, 2)}"
    "  } elseif ([string]$_.Path -match 'dedicated usage') {"
    "   [pscustomobject]@{a = $a; t = 'm'; v = [math]::Round([double]$_.CookedValue)}"
    "  }"
    " }"
    "} | ConvertTo-Json -Compress"
)

_TELEMETRY_TIMEOUT_SECONDS = 8


def _summarize_gpu_telemetry(
    rows: Sequence[dict[str, Any]],
) -> tuple[float | None, int | None] | None:
    """Reduce raw GPU counter samples into one system-level reading.

    Utilization is the busiest physical adapter (its engines summed, capped at
    100%); memory is the dedicated VRAM in use across every adapter. The counters
    are keyed by LUID and ``Win32_VideoController`` does not expose it, so a
    per-adapter breakdown would be fabricated rather than measured.
    """
    engines: dict[str, float] = {}
    memory_total = 0
    saw_memory = False
    for row in rows:
        adapter = row.get("a")
        if not isinstance(adapter, str):
            continue
        value = row.get("v")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        kind = row.get("t")
        if kind == "e":
            key = adapter.split("|", 1)[0]
            engines[key] = engines.get(key, 0.0) + float(value)
        elif kind == "m":
            saw_memory = True
            memory_total += int(value)
    utilization = (
        round(min(100.0, max(0.0, max(engines.values()))), 1) if engines else None
    )
    memory = memory_total if saw_memory else None
    if utilization is None and memory is None:
        return None
    return utilization, memory


def _collect_gpu_telemetry(powershell_path: str) -> tuple[float | None, int | None] | None:
    """Best-effort GPU telemetry; any failure simply leaves telemetry unavailable."""
    try:
        completed = subprocess.run(
            [powershell_path, "-NoProfile", "-NonInteractive", "-Command", _GPU_TELEMETRY_COMMAND],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TELEMETRY_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    raw = completed.stdout.strip()
    if not raw:
        return None
    try:
        payload: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    rows = payload if isinstance(payload, list) else [payload]
    dicts = [row for row in rows if isinstance(row, dict)]
    try:
        summary = _summarize_gpu_telemetry(dicts)
    except (TypeError, ValueError, OverflowError):
        return None
    if summary is None:
        return None
    utilization, memory = summary
    # Dedicated-usage samples are keyed by LUID only. When more than one adapter
    # reports usage the total is multi-GPU VRAM and must not be presented as a
    # single adapter's memory_used_bytes.
    memory_sources = {
        row.get("a")
        for row in dicts
        if row.get("t") == "m" and isinstance(row.get("a"), str)
    }
    if len(memory_sources) > 1:
        memory = None
    return utilization, memory


def normalized_cpu_percent(raw_percent: float, logical_cores: int | None = None) -> float:
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
        # Windows exposes the marketing release via platform.release() ("10"/"11")
        # and "10.0.<build>" via platform.version(). Those two were previously swapped,
        # so the reported build was the release name.
        release = platform.release()
        nt_version = platform.version()
        build = nt_version.rsplit(".", 1)[-1] if "." in nt_version else nt_version
        return OperatingSystemInfo(
            name=platform.system() or "Windows",
            version=release or nt_version,
            build=build,
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
        try:
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
        except subprocess.TimeoutExpired as error:
            # Translate the raw timeout into the adapter's own error so it is reported as
            # "GPU collection timed out" rather than an opaque internal error.
            raise ToolUnavailableError("GPU collection timed out.") from error
        except OSError as error:
            raise ToolUnavailableError("GPU collection could not be started.") from error
        if completed.returncode != 0:
            raise ToolUnavailableError("Windows did not return GPU information.")
        raw = completed.stdout.strip()
        if not raw:
            return ()
        try:
            payload: Any = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ToolUnavailableError("Windows returned invalid GPU information.") from error
        rows = payload if isinstance(payload, list) else [payload]
        results: list[GpuInfo] = []
        try:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                raw_memory = row.get("AdapterRAM")
                memory = int(raw_memory) if raw_memory is not None else None
                if memory in {0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF} or (
                    memory is not None and memory < 0
                ):
                    memory = None
                results.append(
                    GpuInfo(
                        name=str(row.get("Name") or "Unknown GPU"),
                        memory_bytes=memory,
                        driver_version=(
                            str(row["DriverVersion"]) if row.get("DriverVersion") else None
                        ),
                    )
                )
        except (TypeError, ValueError, OverflowError) as error:
            raise ToolUnavailableError("Windows returned invalid GPU information.") from error
        if results and self._powershell_path is not None:
            telemetry = _collect_gpu_telemetry(self._powershell_path)
            if telemetry is not None:
                utilization, memory_used = telemetry
                results[0] = replace(
                    results[0],
                    telemetry_available=True,
                    utilization_percent=utilization,
                    memory_used_bytes=memory_used,
                    # The adapter was created as "telemetry unavailable"; the
                    # placeholder reason has to go, otherwise the invariant in
                    # GpuInfo rejects an available reading that still explains itself.
                    telemetry_limitation=None,
                    telemetry_scope=GPU_TELEMETRY_SYSTEM_SCOPE,
                )
                # The reading is system-wide, so the remaining adapters must not
                # look like they were measured individually.
                for index in range(1, len(results)):
                    results[index] = replace(
                        results[index], telemetry_limitation=GPU_TELEMETRY_UNAVAILABLE_OTHERS
                    )
        return tuple(results)

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
            created_at = process.create_time()
            return ProcessInfo(
                pid=process.pid,
                name=process.name(),
                cpu_percent=normalized_cpu_percent(process.cpu_percent(interval=None)),
                memory_bytes=memory.rss,
                memory_percent=round(process.memory_percent(), 2),
                item_id=process_item_id(process.pid, created_at),
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            return None

    @staticmethod
    def _prime(processes: Sequence[psutil.Process]) -> tuple[psutil.Process, ...]:
        primed: list[psutil.Process] = []
        for process in processes:
            try:
                process.cpu_percent(interval=None)
                primed.append(process)
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
        return tuple(primed)

    @staticmethod
    def _wait(cancel_event: Event | None, sample_seconds: float) -> None:
        if cancel_event is not None:
            if cancel_event.wait(sample_seconds):
                raise ToolCancelledError("Process sampling was cancelled.")
        else:
            time.sleep(sample_seconds)

    def snapshot(
        self,
        limit: int = 200,
        cancel_event: Event | None = None,
        *,
        sample_seconds: float = 0.15,
    ) -> Sequence[ProcessInfo]:
        processes = self._prime(tuple(psutil.process_iter()))
        self._wait(cancel_event, sample_seconds)
        items = [item for process in processes if (item := self._read_process(process))]
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
        processes = self._prime(tuple(psutil.process_iter()))
        self._wait(cancel_event, sample_seconds)
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
