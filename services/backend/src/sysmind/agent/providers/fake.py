from __future__ import annotations

import asyncio
from collections.abc import Sequence

from sysmind.agent.contracts import (
    AgentProvider,
    ProviderAction,
    ProviderName,
    ProviderRequest,
    ProviderResponse,
)


class FakeProvider(AgentProvider):
    def __init__(
        self,
        outcomes: Sequence[ProviderResponse | Exception] = (),
        *,
        delay_seconds: float = 0,
        default_content: str = "Phase 3 离线 Agent Runtime 自检完成。",
    ) -> None:
        self._outcomes = list(outcomes)
        self._delay_seconds = delay_seconds
        self._default = ProviderResponse(
            ProviderAction("finalize", content=default_content),
            metadata={"mode": "deterministic_fake"},
        )
        self.requests: list[ProviderRequest] = []

    @property
    def name(self) -> ProviderName:
        return "fake"

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if self._delay_seconds:
            await asyncio.sleep(self._delay_seconds)
        outcome = self._outcomes.pop(0) if self._outcomes else self._default
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
