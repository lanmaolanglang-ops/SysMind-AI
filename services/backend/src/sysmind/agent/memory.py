from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


def call_signature(name: str, version: str, arguments: dict[str, object]) -> str:
    normalized = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{name}@{version}:{normalized}".encode()).hexdigest()


@dataclass(slots=True)
class WorkingMemory:
    max_observations: int = 16
    rounds: int = 0
    tool_call_count: int = 0
    signatures: set[str] = field(default_factory=set)
    observations: list[dict[str, object]] = field(default_factory=list)

    def remember_tool_result(
        self,
        *,
        name: str,
        version: str,
        arguments: dict[str, object],
        status: str,
        summary: dict[str, object] | None,
        error_code: str | None,
    ) -> None:
        self.signatures.add(call_signature(name, version, arguments))
        self.tool_call_count += 1
        observation: dict[str, object] = {
            "tool": f"{name}@{version}",
            "status": status,
            "summary": summary or {},
        }
        if error_code:
            observation["error_code"] = error_code
        self.observations.append(observation)
        if len(self.observations) > self.max_observations:
            del self.observations[: len(self.observations) - self.max_observations]

    def snapshot(self) -> dict[str, object]:
        return {
            "rounds": self.rounds,
            "tool_call_count": self.tool_call_count,
            "observations": list(self.observations),
        }
