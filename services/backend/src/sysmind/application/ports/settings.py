from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    provider: str
    model: str
    endpoint: str
    secret_reference: str | None
    updated_at: str


class ProviderSettingsRepository(Protocol):
    def get(self) -> ProviderSettings | None: ...
    def save(
        self, provider: str, model: str, endpoint: str, secret_reference: str | None
    ) -> ProviderSettings: ...
    def record_test(
        self, provider: str, status: str, error_code: str | None, duration_ms: int
    ) -> None: ...
