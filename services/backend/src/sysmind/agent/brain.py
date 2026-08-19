from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from threading import Event

from sysmind.agent.context import build_provider_request
from sysmind.agent.contracts import (
    AgentProvider,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderToolCall,
)
from sysmind.agent.memory import WorkingMemory, call_signature
from sysmind.application.ports.agent_tasks import AgentTaskRepository
from sysmind.domain.agent_tasks import AgentEventType, AgentTaskRecord, AgentTaskStatus
from sysmind.tools.executor import ToolExecutionResult, ToolExecutor, arguments_hash
from sysmind.tools.registry import ToolRegistry


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _audit_arguments(arguments: dict[str, object], *, registered: bool) -> dict[str, object]:
    if not registered:
        return {"rejected_unregistered_arguments": True}
    sensitive_keys = {"authorization", "api_key", "token", "password", "secret", "command"}
    return {
        key: "[REDACTED]" if key.casefold() in sensitive_keys else value
        for key, value in arguments.items()
    }


class AgentRunError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AgentBrain:
    def __init__(
        self,
        repository: AgentTaskRepository,
        registry: ToolRegistry,
        executor: ToolExecutor,
        provider: AgentProvider,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._executor = executor
        self._provider = provider

    async def run(self, task: AgentTaskRecord, cancel_event: Event) -> None:
        memory = WorkingMemory()
        self._set_status(task, memory, "planning", progress=5, started_at=_now())
        self._event(task.id, "task.status", {"status": "planning", "progress": 5})
        descriptors = self._registry.descriptors(task.allowed_tools)

        for round_number in range(1, task.budget.max_rounds + 1):
            self._check_cancelled(cancel_event)
            memory.rounds = round_number
            self._set_status(
                task,
                memory,
                "analyzing",
                progress=min(85, 10 + round((round_number - 1) / task.budget.max_rounds * 70)),
            )
            request = build_provider_request(
                user_goal=task.user_goal,
                tools=descriptors,
                memory=memory,
            )
            self._event(
                task.id,
                "provider.started",
                {"provider": self._provider.name, "round": round_number},
            )
            response = await self._call_provider(task.id, request, cancel_event)
            self._event(
                task.id,
                "provider.completed",
                {
                    "provider": self._provider.name,
                    "round": round_number,
                    "action": response.action.type,
                },
            )
            action = response.action
            if action.type == "finalize":
                output = (action.content or "Agent Runtime completed without output.")[:4000]
                self._repository.update(
                    task.id,
                    status="completed",
                    current_round=memory.rounds,
                    tool_call_count=memory.tool_call_count,
                    progress=100,
                    working_summary=memory.snapshot(),
                    finished_at=_now(),
                    final_output=output,
                )
                self._event(
                    task.id,
                    "task.completed",
                    {"status": "completed", "message": output},
                )
                return
            if action.type == "ask_user":
                message = (action.content or "需要更多信息。")[:1000]
                self._repository.update(
                    task.id,
                    status="waiting_user_input",
                    current_round=memory.rounds,
                    tool_call_count=memory.tool_call_count,
                    progress=memory.rounds * 10,
                    working_summary=memory.snapshot(),
                    final_output=message,
                )
                self._event(
                    task.id,
                    "task.message",
                    {"status": "waiting_user_input", "message": message},
                )
                return
            if action.type == "abort":
                raise AgentRunError(
                    "provider_aborted", action.content or "Provider aborted the task."
                )
            if action.type == "propose_action":
                raise AgentRunError(
                    "state_change_rejected",
                    "Phase 3 rejects every proposed system-changing action.",
                )
            if not action.tool_calls:
                raise AgentRunError("provider_protocol_error", "Provider requested no tools.")
            if memory.tool_call_count + len(action.tool_calls) > task.budget.max_tool_calls:
                raise AgentRunError("tool_budget_exceeded", "Agent tool-call budget was exceeded.")

            batch_signatures = [
                call_signature(call.name, call.version, call.arguments)
                for call in action.tool_calls
            ]
            if len(batch_signatures) != len(set(batch_signatures)) or any(
                signature in memory.signatures for signature in batch_signatures
            ):
                raise AgentRunError(
                    "duplicate_tool_call", "A repeated tool call was blocked by the runtime."
                )

            self._set_status(task, memory, "running_tools", progress=min(90, round_number * 20))
            semaphore = asyncio.Semaphore(task.budget.max_parallel_tools)

            async def execute_one(
                index: int,
                batch_semaphore: asyncio.Semaphore = semaphore,
                tool_calls: tuple[ProviderToolCall, ...] = action.tool_calls,
            ) -> tuple[int, ToolExecutionResult]:
                async with batch_semaphore:
                    call = tool_calls[index]
                    return index, await self._execute_tool(task, call, cancel_event)

            indexed_results = await asyncio.gather(
                *(execute_one(index) for index in range(len(action.tool_calls)))
            )
            for index, result in sorted(indexed_results):
                call = action.tool_calls[index]
                memory.remember_tool_result(
                    name=call.name,
                    version=call.version,
                    arguments=call.arguments,
                    status=result.status,
                    summary=result.summary,
                    error_code=result.error_code,
                )
                if result.error_code in {
                    "unknown_tool",
                    "tool_not_allowed",
                    "risk_not_allowed",
                    "privilege_not_allowed",
                    "confirmation_required",
                    "invalid_arguments",
                }:
                    raise AgentRunError(result.error_code, result.error_message or "Tool rejected.")
            self._set_status(task, memory, "planning", progress=min(90, round_number * 20 + 5))

        raise AgentRunError("round_budget_exceeded", "Agent reasoning round budget was exceeded.")

    async def _call_provider(
        self,
        task_id: str,
        request: ProviderRequest,
        cancel_event: Event,
    ) -> ProviderResponse:
        started_at = _now()
        started = time.monotonic()
        response: ProviderResponse | None = None
        error_code: str | None = None
        request_hash = _hash(asdict(request))
        provider_task = asyncio.create_task(self._provider.complete(request))
        try:
            while not provider_task.done():
                if cancel_event.is_set():
                    provider_task.cancel()
                    await asyncio.gather(provider_task, return_exceptions=True)
                    raise AgentRunError("cancelled", "Agent task was cancelled.")
                await asyncio.sleep(0.025)
            response = await provider_task
            return response
        except ProviderError as error:
            error_code = error.code
            raise AgentRunError(error.code, str(error)) from error
        except AgentRunError as error:
            error_code = error.code
            raise
        except asyncio.CancelledError:
            error_code = "cancelled"
            provider_task.cancel()
            await asyncio.gather(provider_task, return_exceptions=True)
            raise
        finally:
            self._repository.add_model_call(
                task_id=task_id,
                provider=self._provider.name,
                status="completed" if response else "failed",
                started_at=started_at,
                finished_at=_now(),
                duration_ms=round((time.monotonic() - started) * 1000),
                request_hash=request_hash,
                response_hash=_hash(asdict(response)) if response else None,
                prompt_tokens=response.prompt_tokens if response else None,
                completion_tokens=response.completion_tokens if response else None,
                error_code=error_code,
            )

    async def _execute_tool(
        self,
        task: AgentTaskRecord,
        tool_call: ProviderToolCall,
        cancel_event: Event,
    ) -> ToolExecutionResult:
        definition = self._registry.get(tool_call.name, tool_call.version)
        risk_level = definition.risk_level if definition else "unknown"
        call_id = str(uuid.uuid4())
        digest = arguments_hash(tool_call.arguments)
        started_at = _now()
        self._repository.create_tool_call(
            call_id=call_id,
            task_id=task.id,
            provider_call_id=tool_call.id,
            tool_name=tool_call.name,
            tool_version=tool_call.version,
            arguments=_audit_arguments(tool_call.arguments, registered=definition is not None),
            arguments_hash=digest,
            risk_level=risk_level,
            started_at=started_at,
        )
        self._event(
            task.id,
            "tool.started",
            {"call_id": call_id, "tool": f"{tool_call.name}@{tool_call.version}"},
        )
        result = await self._executor.execute(
            name=tool_call.name,
            version=tool_call.version,
            arguments=tool_call.arguments,
            allowed_tools=task.allowed_tools,
            cancel_event=cancel_event,
        )
        self._repository.finish_tool_call(
            call_id,
            status=result.status,
            finished_at=_now(),
            duration_ms=result.duration_ms,
            full_result=result.full_result,
            result_summary=result.summary,
            error_code=result.error_code,
            error_message=result.error_message,
        )
        event_type: AgentEventType = (
            "tool.completed" if result.status == "completed" else "tool.failed"
        )
        data: dict[str, object] = {
            "call_id": call_id,
            "tool": f"{tool_call.name}@{tool_call.version}",
            "status": result.status,
            "duration_ms": result.duration_ms,
        }
        if result.error_code:
            data["error_code"] = result.error_code
        self._event(task.id, event_type, data)
        return result

    def _set_status(
        self,
        task: AgentTaskRecord,
        memory: WorkingMemory,
        status: AgentTaskStatus,
        *,
        progress: int,
        started_at: str | None = None,
    ) -> None:
        self._repository.update(
            task.id,
            status=status,
            current_round=memory.rounds,
            tool_call_count=memory.tool_call_count,
            progress=progress,
            working_summary=memory.snapshot(),
            started_at=started_at,
        )

    def _event(self, task_id: str, event_type: AgentEventType, data: dict[str, object]) -> None:
        self._repository.append_event(task_id, event_type, data, _now())

    @staticmethod
    def _check_cancelled(cancel_event: Event) -> None:
        if cancel_event.is_set():
            raise AgentRunError("cancelled", "Agent task was cancelled.")
