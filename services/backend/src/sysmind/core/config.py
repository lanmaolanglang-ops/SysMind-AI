from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sysmind.core.constants import LOOPBACK_HOST


def default_data_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
    return root / "SysMind AI"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SYSMIND_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(default=0, ge=0, le=65535)
    session_token: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(32)),
        min_length=32,
    )
    data_dir: Path = Field(default_factory=default_data_dir)
    log_level: str = "INFO"
    allowed_origins: str = (
        "tauri://localhost,https://tauri.localhost,http://tauri.localhost,"
        "http://localhost:1420,http://127.0.0.1:1420"
    )

    @field_validator("host")
    @classmethod
    def reject_non_loopback(
        cls, value: Literal["127.0.0.1"]
    ) -> Literal["127.0.0.1"]:
        if value != LOOPBACK_HOST:
            raise ValueError("SysMind backend must listen on 127.0.0.1")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported log level")
        return normalized

    @property
    def database_url(self) -> str:
        database_path = (self.data_dir / "sysmind.db").resolve()
        return f"sqlite:///{database_path.as_posix()}"

    @property
    def origin_allowlist(self) -> tuple[str, ...]:
        return tuple(origin.strip() for origin in self.allowed_origins.split(",") if origin.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
