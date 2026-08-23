import ctypes

from sysmind.application.ports.secrets import SecretService
from sysmind.infrastructure.secrets import FakeSecretService
from sysmind.infrastructure.secrets.windows_credential import (
    _CRED_PERSIST_LOCAL_MACHINE,
    _CRED_TYPE_GENERIC,
    WindowsCredentialSecretService,
    _CredentialW,
)


def test_fake_secret_service_is_an_in_memory_port_implementation() -> None:
    service: SecretService = FakeSecretService()

    service.set("provider", "temporary-secret")
    assert service.get("provider") == "temporary-secret"

    service.delete("provider")
    assert service.get("provider") is None


def test_windows_credential_write_is_current_user_and_machine_local() -> None:
    captured: dict[str, object] = {}

    class FakeAdvapi32:
        def CredWriteW(self, pointer: object, flags: int) -> bool:
            credential = ctypes.cast(pointer, ctypes.POINTER(_CredentialW)).contents
            captured.update(
                type=credential.Type,
                target=credential.TargetName,
                persist=credential.Persist,
                username=credential.UserName,
                value=ctypes.string_at(
                    credential.CredentialBlob, credential.CredentialBlobSize
                ).decode("utf-16-le"),
                flags=flags,
            )
            return True

    service = object.__new__(WindowsCredentialSecretService)
    service._namespace = "SysMindAITest"
    service._advapi32 = FakeAdvapi32()

    service.set("provider.api_key", "temporary-secret")

    assert _CRED_PERSIST_LOCAL_MACHINE == 2
    assert captured == {
        "type": _CRED_TYPE_GENERIC,
        "target": "SysMindAITest/provider.api_key",
        "persist": _CRED_PERSIST_LOCAL_MACHINE,
        "username": "SysMind AI Provider",
        "value": "temporary-secret",
        "flags": 0,
    }
