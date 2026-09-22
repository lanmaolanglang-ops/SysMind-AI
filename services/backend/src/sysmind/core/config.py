from __future__ import annotations

import os
import secrets
import threading
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Literal already rejects any non-loopback host at validation time.
    host: Literal["127.0.0.1"] = "127.0.0.1"
    # 0 (default) lets the OS assign an ephemeral port; the bound port is published
    # at startup via the sysmind_endpoint runtime event.
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

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Unsupported log level")
        return normalized

    @property
    def database_url(self) -> str:
        # SQLAlchemy treats the text after sqlite:/// as a filesystem path, so spaces
        # are valid and must not be percent-encoded (that would change the file name).
        database_path = (self.data_dir / "sysmind.db").resolve()
        return f"sqlite:///{database_path.as_posix()}"

    @property
    def origin_allowlist(self) -> tuple[str, ...]:
        return tuple(origin.strip() for origin in self.allowed_origins.split(",") if origin.strip())


_settings: Settings | None = None
_settings_lock = threading.Lock()


def configure_settings(settings: Settings) -> Settings:
    """Install the process-wide settings instance.

    The startup path builds ``Settings`` explicitly (e.g. from CLI arguments) and must
    become the single source of truth so that ``session_token`` — whose default is
    randomly generated per instance — is never produced twice within one process.
    """
    global _settings
    with _settings_lock:
        _settings = settings
    return settings


def get_settings() -> Settings:
    global _settings
    # Double-checked locking: concurrent callers must share one Settings instance,
    # otherwise each default_factory would mint a different session_token.
    if _settings is None:
        with _settings_lock:
            if _settings is None:
                _settings = Settings()
    return _settings
