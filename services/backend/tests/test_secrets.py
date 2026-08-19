from sysmind.application.ports.secrets import SecretService
from sysmind.infrastructure.secrets import FakeSecretService


def test_fake_secret_service_is_an_in_memory_port_implementation() -> None:
    service: SecretService = FakeSecretService()

    service.set("provider", "temporary-secret")
    assert service.get("provider") == "temporary-secret"

    service.delete("provider")
    assert service.get("provider") is None
