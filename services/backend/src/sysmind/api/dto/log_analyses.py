from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sysmind.domain.event_logs import AnalysisStatus, EventLevel, LogAnalysisRecord, LogChannel


class StartLogAnalysisRequest(BaseModel):
    channels: list[LogChannel] = Field(
        default=["Application", "System"], min_length=1, max_length=2
    )
    lookback_hours: int = Field(default=24, ge=1, le=168)
    levels: list[EventLevel] = Field(
        default=["critical", "error", "warning"], min_length=1, max_length=4
    )
    event_ids: list[int] = Field(default_factory=list, max_length=32)
    max_events: int = Field(default=100, ge=1, le=200)

    @field_validator("channels", "levels")
    @classmethod
    def reject_duplicates(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate filters are not allowed")
        return value

    @field_validator("event_ids")
    @classmethod
    def validate_event_ids(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate event IDs are not allowed")
        if any(item < 0 or item > 65535 for item in value):
            raise ValueError("event IDs must be between 0 and 65535")
        return value


class LogAnalysisQueryDto(BaseModel):
    channels: list[LogChannel]
    lookback_hours: int
    levels: list[EventLevel]
    event_ids: list[int]
    max_events: int


class EventEvidenceDto(BaseModel):
    channel: LogChannel
    provider: str
    event_id: int
    level: EventLevel
    timestamp: datetime
    summary: str
    application: str | None = None
    faulting_module: str | None = None
    exception_code: str | None = None


class CrashGroupDto(BaseModel):
    application: str
    faulting_module: str | None
    exception_code: str | None
    count: int
    latest_at: datetime
    evidence_event_ids: list[int]
    providers: list[str]


class EventGroupDto(BaseModel):
    channel: LogChannel
    provider: str
    event_id: int
    level: EventLevel
    count: int
    latest_at: datetime
    sample_summary: str


class LogAnalysisSummaryDto(BaseModel):
    event_count: int
    events: list[EventEvidenceDto]
    event_groups: list[EventGroupDto]
    crash_groups: list[CrashGroupDto]
    notice: str | None = None


class LogAnalysisFailureDto(BaseModel):
    tool: str
    code: str
    message: str


class LogAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: AnalysisStatus
    progress: int = Field(ge=0, le=100)
    current_step: str | None
    started_at: datetime
    finished_at: datetime | None
    query: LogAnalysisQueryDto
    summary: LogAnalysisSummaryDto | None
    failures: list[LogAnalysisFailureDto]
    schema_version: str

    @classmethod
    def from_record(cls, record: LogAnalysisRecord) -> LogAnalysisResponse:
        return cls.model_validate(
            {
                "id": record.id,
                "status": record.status,
                "progress": record.progress,
                "current_step": record.current_step,
                "started_at": record.started_at,
                "finished_at": record.finished_at,
                "query": record.query,
                "summary": record.summary,
                "failures": record.failures,
                "schema_version": record.schema_version,
            }
        )


class LogAnalysisListResponse(BaseModel):
    items: list[LogAnalysisResponse]
