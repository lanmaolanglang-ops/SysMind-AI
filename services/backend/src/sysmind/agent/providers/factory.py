from __future__ import annotations

from pydantic import SecretStr

from sysmind.agent.contracts import AgentProvider
from sysmind.agent.providers.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)

DEFAULT_TIMEOUT_SECONDS = 5.0


class OpenAICompatibleProviderFactory:
    """Default :class:`AgentProviderFactory` for the OpenAI-compatible transport."""

    def __init__(self, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout_seconds = timeout_seconds

    def validate(self, *, endpoint: str, model: str, api_key: str) -> None:
        OpenAICompatibleConfig(endpoint, model, SecretStr(api_key), self._timeout_seconds)

    def build(self, *, endpoint: str, model: str, api_key: str) -> AgentProvider:
        return OpenAICompatibleProvider(
            OpenAICompatibleConfig(endpoint, model, SecretStr(api_key), self._timeout_seconds)
        )
