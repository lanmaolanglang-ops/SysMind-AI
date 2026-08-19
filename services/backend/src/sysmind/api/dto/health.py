from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    backend_version: str
    api_version: str
    ready: bool


class ShutdownResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["shutting_down"] = "shutting_down"

