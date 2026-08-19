from __future__ import annotations

from threading import RLock


class FakeSecretService:
    """In-memory test/development implementation; never persists secrets."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lock = RLock()

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._values[key] = value

    def get(self, key: str) -> str | None:
        with self._lock:
            return self._values.get(key)

    def delete(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)
