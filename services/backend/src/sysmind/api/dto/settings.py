from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProviderSettingsResponse(BaseModel):
    provider: str
    model: str
    endpoint: str
    configured: bool
    updated_at: str | None
    restart_required: bool = False


class UpdateProviderSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(pattern="^openai_compatible$")
    model: str = Field(min_length=1, max_length=120)
    endpoint: HttpUrl
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)


class ProviderTestResponse(BaseModel):
    succeeded: bool
    error_code: str | None
    duration_ms: int
