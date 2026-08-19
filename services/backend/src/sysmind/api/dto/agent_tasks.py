from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from sysmind.agent.contracts import ToolDescriptor
from sysmind.domain.agent_tasks import (
    AgentBudget,
    AgentTaskRecord,
    AgentTaskStatus,
    AgentToolCallRecord,
)


class AgentBudgetRequest(BaseModel):
    max_rounds: int = Field(default=4, ge=1, le=8)
    max_tool_calls: int = Field(default=8, ge=0, le=16)
    timeout_seconds: float = Field(default=30, ge=2, le=120)
    max_parallel_tools: int = Field(default=2, ge=1, le=4)

    def to_domain(self) -> AgentBudget:
        return AgentBudget(**self.model_dump())


class StartAgentTaskRequest(BaseModel):
    user_goal: str = Field(min_length=1, max_length=1000)
    allowed_tools: list[str] = Field(default_factory=list, max_length=16)
    budget: AgentBudgetRequest = Field(default_factory=AgentBudgetRequest)

    @field_validator("user_goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user goal must not be blank")
        return normalized

    @field_validator("allowed_tools")
    @classmethod
    def unique_tools(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate tools are not allowed")
        return value


class AgentBudgetDto(BaseModel):
    max_rounds: int
    max_tool_calls: int
    timeout_seconds: float
    max_parallel_tools: int


class AgentToolCallDto(BaseModel):
    id: str
    provider_call_id: str
    tool_name: str
    tool_version: str
    status: str
    arguments_hash: str
    risk_level: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    result_summary: dict[str, object] | None
    error_code: str | None
    error_message: str | None


class AgentTaskResponse(BaseModel):
    id: str
    status: AgentTaskStatus
    user_goal: str
    provider: str
    allowed_tools: list[str]
    budget: AgentBudgetDto
    current_round: int
    tool_call_count: int
    progress: int = Field(ge=0, le=100)
    working_summary: dict[str, object]
    final_output: str | None
    failure_code: str | None
    failure_message: str | None
    cancel_requested: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    schema_version: str
    tool_calls: list[AgentToolCallDto] = Field(default_factory=list)

    @classmethod
    def from_record(
        cls,
        record: AgentTaskRecord,
        tool_calls: list[AgentToolCallRecord] | None = None,
    ) -> AgentTaskResponse:
        calls = [
            {
                "id": call.id,
                "provider_call_id": call.provider_call_id,
                "tool_name": call.tool_name,
                "tool_version": call.tool_version,
                "status": call.status,
                "arguments_hash": call.arguments_hash,
                "risk_level": call.risk_level,
                "started_at": call.started_at,
                "finished_at": call.finished_at,
                "duration_ms": call.duration_ms,
                "result_summary": call.result_summary,
                "error_code": call.error_code,
                "error_message": call.error_message,
            }
            for call in tool_calls or []
        ]
        return cls.model_validate(
            {
                **asdict(record),
                "allowed_tools": list(record.allowed_tools),
                "budget": asdict(record.budget),
                "tool_calls": calls,
            }
        )


class AgentTaskListResponse(BaseModel):
    items: list[AgentTaskResponse]


class ToolDescriptorDto(BaseModel):
    name: str
    version: str
    qualified_name: str
    description: str
    input_schema: dict[str, object]
    risk_level: str
    sensitivity: list[str]

    @classmethod
    def from_descriptor(cls, descriptor: ToolDescriptor) -> ToolDescriptorDto:
        return cls(
            name=descriptor.name,
            version=descriptor.version,
            qualified_name=descriptor.qualified_name,
            description=descriptor.description,
            input_schema=descriptor.input_schema,
            risk_level=descriptor.risk_level,
            sensitivity=list(descriptor.sensitivity),
        )


class ToolCatalogResponse(BaseModel):
    items: list[ToolDescriptorDto]
