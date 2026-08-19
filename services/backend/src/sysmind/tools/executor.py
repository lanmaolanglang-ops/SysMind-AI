from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from threading import Event

from pydantic import ValidationError

from sysmind.tools.contracts import (
    ToolCancelledError,
    ToolPermissionError,
    ToolUnavailableError,
)
from sysmind.tools.policy import ToolPolicy, ToolPolicyError


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    status: str
    arguments_hash: str
    duration_ms: int
    full_result: object | None = None
    summary: dict[str, object] | None = None
    error_code: str | None = None
    error_message: str | None = None


def arguments_hash(arguments: dict[str, object]) -> str:
    encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class ToolExecutor:
    def __init__(self, policy: ToolPolicy, *, max_parallel: int = 4) -> None:
        if not 1 <= max_parallel <= 8:
            raise ValueError("Tool executor parallelism must be between 1 and 8.")
        self._policy = policy
        self._global_semaphore = asyncio.Semaphore(max_parallel)
        self._key_semaphores: dict[str, asyncio.Semaphore] = {}

    async def execute(
        self,
        *,
        name: str,
        version: str,
        arguments: dict[str, object],
        allowed_tools: tuple[str, ...],
        cancel_event: Event,
    ) -> ToolExecutionResult:
        started = time.monotonic()
        digest = arguments_hash(arguments)
        try:
            definition = self._policy.authorize(
                name=name, version=version, allowed_tools=allowed_tools
            )
            validated = definition.input_model.model_validate(arguments)
        except ToolPolicyError as error:
            return self._error(error.code, str(error), digest, started)
        except ValidationError:
            return self._error(
                "invalid_arguments",
                "Tool arguments do not match the registered schema.",
                digest,
                started,
            )
        if cancel_event.is_set():
            return self._error("cancelled", "Tool execution was cancelled.", digest, started)
        key_semaphore = self._key_semaphores.setdefault(
            definition.concurrency_key, asyncio.Semaphore(1)
        )
        try:
            async with self._global_semaphore, key_semaphore:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(definition.handler, validated, cancel_event),
                    timeout=definition.timeout_seconds,
                )
            normalized = definition.output_adapter.dump_python(
                definition.output_adapter.validate_python(raw), mode="json"
            )
            return ToolExecutionResult(
                status="completed",
                arguments_hash=digest,
                duration_ms=round((time.monotonic() - started) * 1000),
                full_result=normalized,
                summary=definition.summarizer(normalized),
            )
        except TimeoutError:
            return self._error("timeout", "Tool execution timed out.", digest, started)
        except ToolCancelledError:
            return self._error("cancelled", "Tool execution was cancelled.", digest, started)
        except ToolPermissionError as error:
            return self._error("permission_required", str(error), digest, started)
        except ToolUnavailableError as error:
            return self._error("unsupported", str(error), digest, started)
        except Exception:
            return self._error(
                "internal_error",
                "The tool failed without exposing sensitive details.",
                digest,
                started,
            )

    @staticmethod
    def _error(code: str, message: str, digest: str, started: float) -> ToolExecutionResult:
        return ToolExecutionResult(
            status="failed" if code != "cancelled" else "cancelled",
            arguments_hash=digest,
            duration_ms=round((time.monotonic() - started) * 1000),
            error_code=code,
            error_message=message,
        )
