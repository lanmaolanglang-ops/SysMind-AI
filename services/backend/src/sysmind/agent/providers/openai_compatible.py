from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from pydantic import SecretStr

from sysmind.agent.contracts import (
    AgentProvider,
    ProviderAction,
    ProviderActionType,
    ProviderName,
    ProviderProtocolError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderToolCall,
    ProviderTransportError,
    ToolDescriptor,
)

_ACTION_TYPES = {"finalize", "ask_user", "abort", "propose_action"}


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: SecretStr
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("Provider base URL must use HTTPS or an HTTP loopback address.")
        if not self.model.strip():
            raise ValueError("Provider model must not be empty.")
        if not 1 <= self.timeout_seconds <= 120:
            raise ValueError("Provider timeout must be between 1 and 120 seconds.")


def _wire_name(tool: ToolDescriptor) -> str:
    raw = f"{tool.name}__v{tool.version}"
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:64]


def _tool_payload(tool: ToolDescriptor) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": _wire_name(tool),
            "description": f"{tool.description} Exact tool: {tool.qualified_name}",
            "parameters": tool.input_schema,
        },
    }


class OpenAICompatibleProvider(AgentProvider):
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client

    @property
    def name(self) -> ProviderName:
        return "openai_compatible"

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        tool_map = {_wire_name(tool): tool for tool in request.tools}
        if len(tool_map) != len(request.tools):
            raise ProviderProtocolError("Tool names collide after provider-safe encoding.")
        messages: list[dict[str, object]] = [
            {
                "role": "system",
                "content": request.system_prompt
                if request.response_format == "structured_plan"
                else (
                    f"{request.system_prompt}\n"
                    "When not calling a tool, return JSON with action finalize, ask_user, or abort "
                    "and a user-visible content string."
                ),
            },
            {"role": "user", "content": request.user_goal},
            *request.messages,
        ]
        payload: dict[str, object] = {
            "model": self._config.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": 0,
        }
        if request.tools:
            payload["tools"] = [_tool_payload(tool) for tool in request.tools]
            payload["tool_choice"] = "auto"
        try:
            response = await self._post(payload)
        except httpx.TimeoutException as error:
            raise ProviderTimeoutError("The model provider timed out.") from error
        except httpx.RequestError as error:
            raise ProviderTransportError(
                "The model provider connection was interrupted."
            ) from error
        if response.status_code == 429:
            raise ProviderRateLimitError("The model provider rate limit was reached.")
        if response.status_code >= 400:
            raise ProviderTransportError(
                f"The model provider returned HTTP {response.status_code}."
            )
        try:
            body = cast(dict[str, Any], response.json())
            choice = body["choices"][0]
            message = choice["message"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderProtocolError(
                "The model provider returned an invalid response."
            ) from error

        action = self._parse_action(message, tool_map)
        usage = body.get("usage") or {}
        return ProviderResponse(
            action=action,
            prompt_tokens=_optional_int(usage.get("prompt_tokens")),
            completion_tokens=_optional_int(usage.get("completion_tokens")),
            provider_request_id=(str(body["id"]) if body.get("id") else None),
        )

    async def _post(self, payload: dict[str, object]) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        endpoint = f"{self._config.base_url.rstrip('/')}/chat/completions"
        if self._client is not None:
            return await self._client.post(endpoint, headers=headers, json=payload)
        async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
            return await client.post(endpoint, headers=headers, json=payload)

    @staticmethod
    def _parse_action(
        message: dict[str, Any], tool_map: dict[str, ToolDescriptor]
    ) -> ProviderAction:
        raw_calls = message.get("tool_calls") or []
        if raw_calls:
            calls: list[ProviderToolCall] = []
            for raw in raw_calls:
                try:
                    function = raw["function"]
                    descriptor = tool_map[function["name"]]
                    arguments = json.loads(function.get("arguments") or "{}")
                    if not isinstance(arguments, dict):
                        raise TypeError
                    calls.append(
                        ProviderToolCall(
                            id=str(raw["id"]),
                            name=descriptor.name,
                            version=descriptor.version,
                            arguments=cast(dict[str, object], arguments),
                        )
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                    raise ProviderProtocolError(
                        "The provider returned an invalid tool call."
                    ) from error
            return ProviderAction("request_tool_calls", tool_calls=tuple(calls))

        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderProtocolError("The provider response has no usable content.")
        # The agent prompt requires a JSON object, so unstructured prose is a
        # protocol violation like every other malformed branch above. Silently
        # finalising here made the brain path complete the task with model noise
        # and gave the caller no way to tell a real answer from garbage.
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise ProviderProtocolError(
                "The provider returned unstructured content where an action was required."
            ) from error
        if not isinstance(parsed, dict):
            raise ProviderProtocolError("The provider action must be a JSON object.")
        if {"problem_category", "confidence", "status", "steps"} <= parsed.keys():
            return ProviderAction(
                "finalize",
                content=json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))[:4000],
            )
        action_value = parsed.get("action")
        action_content = parsed.get("content")
        if action_value not in _ACTION_TYPES or not isinstance(action_content, str):
            raise ProviderProtocolError("The provider returned an unsupported action.")
        return ProviderAction(cast(ProviderActionType, action_value), content=action_content[:4000])


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None
