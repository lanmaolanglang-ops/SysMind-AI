from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from sysmind.api.app import create_app
from sysmind.core.config import Settings
from sysmind.runtime.shutdown import ShutdownController

TEST_TOKEN = "test-session-token-that-is-long-enough"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, session_token=SecretStr(TEST_TOKEN))


@pytest.fixture
def shutdown_controller() -> ShutdownController:
    return ShutdownController()


@pytest.fixture
def client(settings: Settings, shutdown_controller: ShutdownController) -> Iterator[TestClient]:
    with TestClient(create_app(settings, shutdown_controller)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(settings: Settings) -> dict[str, str]:
    # Derive the header from the settings fixture so the token is defined in one place.
    return {
        "X-SysMind-Session": settings.session_token.get_secret_value(),
        "Origin": "tauri://localhost",
    }
