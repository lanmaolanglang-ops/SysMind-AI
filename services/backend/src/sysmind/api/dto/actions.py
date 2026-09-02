from __future__ import annotations

from dataclasses import asdict

from pydantic import BaseModel, Field

from sysmind.domain.actions import ActionRecord, ProcessActionCandidate, StartupActionCandidate


class CandidateResponse(BaseModel):
    item_id: str
    name: str
    source_kind: str
    command_name: str | None
    observed_revision: str


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]


class ProcessCandidateResponse(BaseModel):
    item_id: str
    name: str
    source_kind: str
    command_name: str | None
    observed_revision: str
    cpu_percent: float
    memory_percent: float


class ProcessCandidateListResponse(BaseModel):
    items: list[ProcessCandidateResponse]


class CreateActionRequest(BaseModel):
    diagnosis_id: str = Field(min_length=36, max_length=36)
    item_id: str = Field(min_length=64, max_length=64)
    observed_revision: str = Field(min_length=64, max_length=64)


class CreateProcessActionRequest(CreateActionRequest):
    pass


class ExecuteActionRequest(BaseModel):
    ticket: str = Field(min_length=20, max_length=4096)


class ActionResponse(BaseModel):
    id: str
    plan_id: str
    diagnosis_id: str
    tool_name: str
    tool_version: str
    target_name: str
    source_kind: str
    status: str
    recovery_available: bool
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: ActionRecord) -> ActionResponse:
        data = asdict(record)
        for key in ("target_id", "observed_revision", "recovery_id"):
            data.pop(key)
        data["recovery_available"] = record.recovery_id is not None and record.status in {
            "succeeded",
            "verification_failed",
        }
        return cls.model_validate(data)


class ActionListResponse(BaseModel):
    items: list[ActionResponse]


class ConsentResponse(BaseModel):
    action: ActionResponse
    ticket: str | None
    expires_at: str | None


def candidate_response(item: StartupActionCandidate) -> CandidateResponse:
    return CandidateResponse.model_validate(asdict(item))


def process_candidate_response(item: ProcessActionCandidate) -> ProcessCandidateResponse:
    data = asdict(item)
    data.pop("pid")
    return ProcessCandidateResponse.model_validate(data)
