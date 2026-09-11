from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from sysmind.agent.contracts import AgentProvider, ProviderError, ProviderRequest
from sysmind.application.ports.agent_providers import AgentProviderFactory
from sysmind.application.ports.secrets import SecretService
from sysmind.application.ports.settings import ProviderSettingsRepository
from sysmind.observability.logging import log_event

_SECRET_REFERENCE = "provider.api_key"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PublicProviderSettings:
    provider: str
    model: str
    endpoint: str
    configured: bool
    updated_at: str | None


class ProviderSettingsService:
    def __init__(
        self,
        repository: ProviderSettingsRepository,
        secrets: SecretService,
        provider_factory: AgentProviderFactory,
    ) -> None:
        self._repository = repository
        self._secrets = secrets
        self._provider_factory = provider_factory

    def get(self) -> PublicProviderSettings:
        settings = self._repository.get()
        if settings is None:
            return PublicProviderSettings("local-rules", "", "", False, None)
        configured = bool(
            settings.secret_reference and self._secrets.get(settings.secret_reference)
        )
        return PublicProviderSettings(
            settings.provider,
            settings.model,
            settings.endpoint,
            configured,
            settings.updated_at,
        )

    def save(
        self, provider: str, model: str, endpoint: str, api_key: str | None
    ) -> PublicProviderSettings:
        if provider != "openai_compatible":
            raise ValueError("Unsupported provider.")
        previous_secret = self._secrets.get(_SECRET_REFERENCE)
        candidate_secret = api_key or previous_secret
        if not candidate_secret:
            raise ValueError("Provider API key is required.")
        # Validate the same normalized values that will be persisted, so validation and
        # storage can never disagree about what was saved.
        normalized_model = model.strip()
        normalized_endpoint = endpoint.rstrip("/")
        self._provider_factory.validate(
            endpoint=normalized_endpoint, model=normalized_model, api_key=candidate_secret
        )
        if api_key:
            self._secrets.set(_SECRET_REFERENCE, api_key)
        try:
            self._repository.save(
                provider, normalized_model, normalized_endpoint, _SECRET_REFERENCE
            )
        except Exception:
            if api_key:
                if previous_secret is None:
                    self._secrets.delete(_SECRET_REFERENCE)
                else:
                    self._secrets.set(_SECRET_REFERENCE, previous_secret)
            raise
        del candidate_secret
        return self.get()

    def clear_credential(self) -> PublicProviderSettings:
        settings = self._repository.get()
        self._secrets.delete(_SECRET_REFERENCE)
        if settings is not None:
            self._repository.save(settings.provider, settings.model, settings.endpoint, None)
        return self.get()

    def configured_provider(self) -> AgentProvider | None:
        settings = self._repository.get()
        if settings is None or settings.provider != "openai_compatible":
            return None
        api_key = (
            self._secrets.get(settings.secret_reference) if settings.secret_reference else None
        )
        if not api_key:
            return None
        return self._provider_factory.build(
            endpoint=settings.endpoint, model=settings.model, api_key=api_key
        )

    async def test_connection(self) -> tuple[bool, str | None, int]:
        # Resolving the provider reads SQLite and the Windows credential store, both
        # blocking; keep them off the event loop.
        provider = await asyncio.to_thread(self.configured_provider)
        if provider is None:
            raise ValueError("Provider credential is not configured.")
        started = time.monotonic()
        error_code: str | None = None
        try:
            await provider.complete(
                ProviderRequest(
                    system_prompt="Return a short connectivity acknowledgement.",
                    user_goal="Connection test",
                    tools=(),
                    messages=(),
                    max_output_tokens=16,
                )
            )
            succeeded = True
        except ProviderError as error:
            succeeded = False
            error_code = error.code
        except Exception as error:
            # An unexpected adapter failure must still land in the connection-test
            # audit trail and degrade to the local-rules fallback, never a 500.
            succeeded = False
            error_code = "internal_error"
            log_event(
                _LOGGER,
                logging.ERROR,
                "Provider connection test failed unexpectedly.",
                component="provider_settings",
                event_type="provider_test_failed",
                error_type=type(error).__name__,
            )
        duration_ms = round((time.monotonic() - started) * 1000)
        self._repository.record_test(
            provider.name, "succeeded" if succeeded else "failed", error_code, duration_ms
        )
        return succeeded, error_code, duration_ms
