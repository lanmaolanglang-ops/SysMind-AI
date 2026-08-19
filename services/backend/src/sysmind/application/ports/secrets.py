from typing import Protocol


class SecretService(Protocol):
    """Stores opaque secrets outside ordinary application persistence."""

    def set(self, key: str, value: str) -> None: ...

    def get(self, key: str) -> str | None: ...

    def delete(self, key: str) -> None: ...
