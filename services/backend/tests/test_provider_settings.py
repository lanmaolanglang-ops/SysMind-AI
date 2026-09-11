from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from sysmind.agent.providers import OpenAICompatibleProviderFactory
from sysmind.api.app import create_app
from sysmind.application.services.provider_settings import ProviderSettingsService
from sysmind.core.config import Settings
from sysmind.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    run_migrations,
)
from sysmind.infrastructure.database.repositories.settings import (
    SqlAlchemyProviderSettingsRepository,
)
from sysmind.infrastructure.secrets import FakeSecretService


def test_provider_settings_store_only_opaque_reference_and_never_return_key(
    tmp_path: Path,
) -> None:
    token = "provider-settings-session-token-long-enough"
    settings = Settings(data_dir=tmp_path, session_token=SecretStr(token))
    run_migrations(settings.database_url)
    secrets = FakeSecretService()
    service = ProviderSettingsService(
        SqlAlchemyProviderSettingsRepository(
            create_session_factory(settings.database_url)
        ),
        secrets,
        OpenAICompatibleProviderFactory(),
    )
    headers = {"X-SysMind-Session": token, "Origin": "tauri://localhost"}

    with TestClient(create_app(settings, provider_settings_service=service)) as client:
        saved = client.put(
            "/api/v1/settings",
            headers=headers,
            json={
                "provider": "openai_compatible",
                "model": "fixture-model",
                "endpoint": "https://provider.example/v1",
                "api_key": "super-secret-provider-key",
            },
        )
        read = client.get("/api/v1/settings", headers=headers)

    assert saved.status_code == 200
    assert read.json()["configured"] is True
    assert "api_key" not in read.text
    assert "super-secret-provider-key" not in (tmp_path / "sysmind.db").read_bytes().decode(
        "utf-8", errors="ignore"
    )
    assert secrets.get("provider.api_key") == "super-secret-provider-key"


def test_provider_endpoint_rejects_insecure_remote_http(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'settings.db').as_posix()}"
    run_migrations(database_url)
    service = ProviderSettingsService(
        SqlAlchemyProviderSettingsRepository(create_session_factory(database_url)),
        FakeSecretService(),
        OpenAICompatibleProviderFactory(),
    )

    try:
        service.save("openai_compatible", "model", "http://remote.example/v1", "secret")
    except ValueError as error:
        assert "HTTPS" in str(error)
    else:
        raise AssertionError("insecure remote endpoint was accepted")


@pytest.mark.anyio
async def test_provider_test_connection_maps_unexpected_errors_to_failed_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'settings.db').as_posix()}"
    run_migrations(database_url)
    service = ProviderSettingsService(
        SqlAlchemyProviderSettingsRepository(create_session_factory(database_url)),
        FakeSecretService(),
        OpenAICompatibleProviderFactory(),
    )

    class ExplodingProvider:
        name = "exploding"

        async def complete(self, request: object) -> object:
            raise RuntimeError("simulated adapter crash")

    monkeypatch.setattr(service, "configured_provider", lambda: ExplodingProvider())

    succeeded, error_code, duration_ms = await service.test_connection()

    assert succeeded is False
    assert error_code == "internal_error"
    assert duration_ms >= 0
    engine = create_database_engine(database_url)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT provider, status, error_code FROM provider_connection_tests")
        ).one()
    engine.dispose()
    assert row == ("exploding", "failed", "internal_error")
