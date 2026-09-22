from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from sysmind.agent.contracts import (
    ProviderProtocolError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderTransportError,
    ToolDescriptor,
)
from sysmind.agent.providers import OpenAICompatibleConfig, OpenAICompatibleProvider


def _request() -> ProviderRequest:
    return ProviderRequest(
        system_prompt="bounded policy",
        user_goal="read one value",
        tools=(
            ToolDescriptor(
                "test.echo",
                "1.0",
                "test tool",
                {"type": "object", "properties": {"value": {"type": "integer"}}},
                "read_only",
                (),
            ),
        ),
    )


def _config() -> OpenAICompatibleConfig:
    return OpenAICompatibleConfig(
        "https://provider.example/v1", "fixture-model", SecretStr("never-log-this-key")
    )


@pytest.mark.anyio
async def test_openai_compatible_maps_structured_tool_call_without_exposing_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer never-log-this-key"
        body = json.loads(request.content)
        assert body["tools"][0]["function"]["name"] == "test_echo__v1_0"
        return httpx.Response(
            200,
            json={
                "id": "provider-request-1",
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "test_echo__v1_0",
                                        "arguments": '{"value":7}',
                                    },
                                }
                            ]
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(_config(), client=client)
        response = await provider.complete(_request())

    assert response.action.tool_calls[0].name == "test.echo"
    assert response.action.tool_calls[0].arguments == {"value": 7}
    assert "never-log-this-key" not in repr(_config())


@pytest.mark.anyio
async def test_openai_compatible_preserves_structured_diagnosis_plan() -> None:
    plan = {
        "problem_category": "performance",
        "confidence": 0.82,
        "status": "ready",
        "clarification_question": None,
        "steps": [{"tool": "test.echo@1.0", "reason": "check value", "arguments": {"value": 1}}],
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(plan)}}]},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await OpenAICompatibleProvider(_config(), client=client).complete(_request())

    assert response.action.type == "finalize"
    assert json.loads(response.action.content or "{}") == plan


@pytest.mark.anyio
async def test_openai_compatible_maps_rate_limit() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(429))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAICompatibleProvider(_config(), client=client)
        with pytest.raises(ProviderRateLimitError):
            await provider.complete(_request())


@pytest.mark.anyio
async def test_openai_compatible_rejects_truncated_response() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=b'{"choices":'))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAICompatibleProvider(_config(), client=client)
        with pytest.raises(ProviderProtocolError):
            await provider.complete(_request())


@pytest.mark.anyio
async def test_openai_compatible_maps_interrupted_transport() -> None:
    def interrupted(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("stream ended", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(interrupted)) as client:
        provider = OpenAICompatibleProvider(_config(), client=client)
        with pytest.raises(ProviderTransportError):
            await provider.complete(_request())


def test_openai_compatible_rejects_non_tls_remote_base_url() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAICompatibleConfig("http://provider.example/v1", "model", SecretStr("secret"))


@pytest.mark.anyio
async def test_openai_compatible_rejects_unstructured_prose() -> None:
    """The agent prompt demands JSON, so prose is a protocol violation.

    It used to be silently wrapped in a `finalize` action, which made the brain
    path complete the task with model noise and gave the caller no way to tell a
    real answer from a malformed one.
    """
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200, json={"choices": [{"message": {"content": "我觉得磁盘没问题。"}}]}
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAICompatibleProvider(_config(), client=client)
        with pytest.raises(ProviderProtocolError, match="unstructured"):
            await provider.complete(_request())


def test_provider_names_come_from_the_central_enum() -> None:
    from sysmind.agent.contracts import KNOWN_PROVIDER_NAMES
    from sysmind.agent.providers import FakeProvider

    assert FakeProvider().name in KNOWN_PROVIDER_NAMES
    assert OpenAICompatibleProvider(_config()).name in KNOWN_PROVIDER_NAMES
