from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from sysmind.application.ports.settings import ProviderSettings
from sysmind.infrastructure.database.models import (
    ProviderConnectionTestModel,
    ProviderSettingsModel,
)


class SqlAlchemyProviderSettingsRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def get(self) -> ProviderSettings | None:
        with self._sessions() as session:
            row = session.get(ProviderSettingsModel, 1)
            return self._record(row) if row else None

    def save(
        self, provider: str, model: str, endpoint: str, secret_reference: str | None
    ) -> ProviderSettings:
        now = datetime.now(UTC)
        with self._sessions.begin() as session:
            row = session.get(ProviderSettingsModel, 1)
            if row is None:
                row = ProviderSettingsModel(id=1)
                session.add(row)
            row.provider = provider
            row.model = model
            row.endpoint = endpoint
            row.secret_reference = secret_reference
            row.updated_at = now
            session.flush()
            return self._record(row)

    def record_test(
        self, provider: str, status: str, error_code: str | None, duration_ms: int
    ) -> None:
        with self._sessions.begin() as session:
            session.add(
                ProviderConnectionTestModel(
                    provider=provider,
                    status=status,
                    error_code=error_code,
                    duration_ms=duration_ms,
                    created_at=datetime.now(UTC),
                )
            )

    @staticmethod
    def _record(row: ProviderSettingsModel) -> ProviderSettings:
        return ProviderSettings(
            row.provider,
            row.model,
            row.endpoint,
            row.secret_reference,
            row.updated_at.isoformat(),
        )
