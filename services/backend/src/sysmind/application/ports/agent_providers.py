from __future__ import annotations

from typing import Protocol

from sysmind.agent.contracts import AgentProvider


class AgentProviderFactory(Protocol):
    """Port for validating provider settings and building a concrete provider.

    The application layer depends on this port instead of importing a concrete provider
    class, so supporting another provider (or another transport) never requires editing
    application services. The composition root supplies the implementation.
    """

    def validate(self, *, endpoint: str, model: str, api_key: str) -> None:
        """Raise ``ValueError`` when the combination is not a supported configuration."""
        ...

    def build(self, *, endpoint: str, model: str, api_key: str) -> AgentProvider: ...
