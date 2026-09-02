from __future__ import annotations

import subprocess
import sys
import time
from threading import Event

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter

from sysmind.tools.executor import ToolExecutor
from sysmind.tools.policy import ToolPolicy
from sysmind.tools.registry import ToolDefinition, ToolRegistry, ToolRegistryError


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def test_executor_can_be_imported_without_agent_import_order_dependency() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import sysmind.tools.executor"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def _definition(
    *,
    name: str = "test.safe",
    risk: str = "read_only",
    timeout: float = 1,
    handler=None,  # type: ignore[no-untyped-def]
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        version="1.0",
        description="A deterministic test tool.",
        input_model=EmptyInput,
        output_adapter=TypeAdapter(dict[str, int]),
        risk_level=risk,  # type: ignore[arg-type]
        required_privilege="user",
        sensitivity=(),
        timeout_seconds=timeout,
        concurrency_key="test",
        confirmation_policy="none",
        handler=handler or (lambda _input, _cancel: {"value": 1}),
        summarizer=lambda value: {"value": value["value"]},  # type: ignore[index]
    )


def test_registry_rejects_duplicates_and_invalid_names() -> None:
    definition = _definition()
    registry = ToolRegistry((definition,))
    with pytest.raises(ToolRegistryError, match="Duplicate"):
        registry.register(definition)
    with pytest.raises(ToolRegistryError, match="Invalid tool name"):
        ToolRegistry((_definition(name="Shell Execute"),))


@pytest.mark.anyio
async def test_policy_rejects_state_change_even_when_task_lists_it() -> None:
    definition = _definition(name="test.change", risk="state_change")
    executor = ToolExecutor(ToolPolicy(ToolRegistry((definition,))))
    result = await executor.execute(
        name="test.change",
        version="1.0",
        arguments={},
        allowed_tools=("test.change@1.0",),
        cancel_event=Event(),
    )
    assert result.error_code == "risk_not_allowed"


@pytest.mark.anyio
async def test_tool_timeout_and_cancellation_have_stable_errors() -> None:
    def slow(_input: BaseModel, _cancel: Event) -> object:
        time.sleep(0.08)
        return {"value": 1}

    definition = _definition(timeout=0.01, handler=slow)
    executor = ToolExecutor(ToolPolicy(ToolRegistry((definition,))))
    timeout_result = await executor.execute(
        name="test.safe",
        version="1.0",
        arguments={},
        allowed_tools=("test.safe@1.0",),
        cancel_event=Event(),
    )
    cancelled = Event()
    cancelled.set()
    cancelled_result = await executor.execute(
        name="test.safe",
        version="1.0",
        arguments={},
        allowed_tools=("test.safe@1.0",),
        cancel_event=cancelled,
    )
    assert timeout_result.error_code == "timeout"
    assert cancelled_result.error_code == "cancelled"
