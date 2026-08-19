import pytest
from pydantic import SecretStr, ValidationError

from sysmind.core.config import Settings


def test_settings_force_loopback(tmp_path: object) -> None:
    with pytest.raises(ValidationError):
        Settings(
            host="0.0.0.0",  # type: ignore[arg-type]
            data_dir=tmp_path,
            session_token=SecretStr("a" * 32),
        )


def test_settings_do_not_expose_token(tmp_path: object) -> None:
    settings = Settings(data_dir=tmp_path, session_token=SecretStr("secret-value" * 3))

    assert "secret-value" not in repr(settings)
    assert settings.session_token.get_secret_value().startswith("secret-value")


def test_settings_accept_inherited_session_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("SYSMIND_SESSION_TOKEN", "inherited-session-token-that-is-long-enough")

    settings = Settings(data_dir=tmp_path)

    assert (
        settings.session_token.get_secret_value()
        == "inherited-session-token-that-is-long-enough"
    )
