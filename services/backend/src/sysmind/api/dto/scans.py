from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from sysmind.domain.diagnostics import (
    GPU_TELEMETRY_ADAPTER_SCOPE,
    ScanRecord,
    ScanStatus,
)


class CapabilityDto(BaseModel):
    name: str
    available: bool
    reason: str | None = None


class OperatingSystemDto(BaseModel):
    name: str
    version: str
    build: str
    architecture: str


class CpuDto(BaseModel):
    model: str
    physical_cores: int
    logical_cores: int
    utilization_percent: float
    frequency_mhz: float | None


class GpuDto(BaseModel):
    name: str
    memory_bytes: int | None
    driver_version: str | None
    telemetry_available: bool = False
    utilization_percent: float | None = None
    memory_used_bytes: int | None = None
    telemetry_limitation: str | None = None
    telemetry_scope: str = GPU_TELEMETRY_ADAPTER_SCOPE


class MemoryDto(BaseModel):
    total_bytes: int
    available_bytes: int
    used_bytes: int
    utilization_percent: float


class DiskDto(BaseModel):
    volume: str
    mountpoint: str
    filesystem: str
    total_bytes: int
    free_bytes: int
    used_bytes: int
    utilization_percent: float


class ProcessDto(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_bytes: int
    memory_percent: float


class ScanFailureDto(BaseModel):
    tool: str
    code: str
    message: str


class ScanSummaryDto(BaseModel):
    capabilities: list[CapabilityDto] = Field(default_factory=list)
    operating_system: OperatingSystemDto | None = None
    cpu: CpuDto | None = None
    gpus: list[GpuDto] = Field(default_factory=list)
    memory: MemoryDto | None = None
    disks: list[DiskDto] = Field(default_factory=list)
    processes: list[ProcessDto] = Field(default_factory=list)
    high_usage_processes: list[ProcessDto] = Field(default_factory=list)


class ScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: ScanStatus
    progress: int = Field(ge=0, le=100)
    current_step: str | None
    started_at: datetime
    finished_at: datetime | None
    summary: ScanSummaryDto | None
    failures: list[ScanFailureDto]
    schema_version: str

    @classmethod
    def from_record(cls, record: ScanRecord) -> ScanResponse:
        return cls.model_validate(
            {
                "id": record.id,
                "status": record.status,
                "progress": record.progress,
                "current_step": record.current_step,
                "started_at": record.started_at,
                "finished_at": record.finished_at,
                "summary": record.summary,
                "failures": record.failures,
                "schema_version": record.schema_version,
            }
        )


class ScanListResponse(BaseModel):
    items: list[ScanResponse]
