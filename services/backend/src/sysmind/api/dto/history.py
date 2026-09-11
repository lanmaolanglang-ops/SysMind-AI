from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel, ConfigDict, Field

from sysmind.domain.history import BaselineMetric, CleanupResult, DeletionImpact


class DeletionImpactResponse(BaseModel):
    kind: str
    record_id: str
    revision: str
    deletable: bool
    dependent_records: int
    protected_reason: str | None

    @classmethod
    def from_value(cls, value: DeletionImpact) -> DeletionImpactResponse:
        return cls(**asdict(value))


class ConfirmDeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str = Field(min_length=64, max_length=64, pattern="^[a-f0-9]+$")


class RetentionPolicyResponse(BaseModel):
    retention_days: int


class UpdateRetentionPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retention_days: int = Field(ge=7, le=3650)


class CleanupResponse(BaseModel):
    deleted_scans: int
    deleted_diagnoses: int
    deleted_log_analyses: int
    protected_records: int
    completed_at: str

    @classmethod
    def from_value(cls, value: CleanupResult) -> CleanupResponse:
        return cls(**asdict(value))


class BaselineMetricResponse(BaseModel):
    metric: str
    samples: int
    median: float
    latest: float
    delta: float

    @classmethod
    def from_value(cls, value: BaselineMetric) -> BaselineMetricResponse:
        return cls(**asdict(value))


class DeletionResponse(BaseModel):
    deleted: bool = True


class BaselineResponse(BaseModel):
    items: list[BaselineMetricResponse]
