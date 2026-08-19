from __future__ import annotations

from dataclasses import dataclass

from sysmind.tools.registry import ToolDefinition, ToolRegistry


class ToolPolicyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    registry: ToolRegistry
    allowed_risk_levels: tuple[str, ...] = ("read_only",)

    def authorize(
        self,
        *,
        name: str,
        version: str,
        allowed_tools: tuple[str, ...],
    ) -> ToolDefinition:
        qualified = f"{name}@{version}"
        definition = self.registry.get(name, version)
        if definition is None:
            raise ToolPolicyError("unknown_tool", "The requested tool is not registered.")
        if qualified not in allowed_tools:
            raise ToolPolicyError("tool_not_allowed", "The tool is outside this task's scope.")
        if definition.risk_level not in self.allowed_risk_levels:
            raise ToolPolicyError(
                "risk_not_allowed", "The tool risk is outside this task's declared scope."
            )
        if definition.required_privilege != "user":
            raise ToolPolicyError(
                "privilege_not_allowed", "The tool requires an unavailable privilege."
            )
        if definition.confirmation_policy != "none":
            raise ToolPolicyError(
                "confirmation_required", "Phase 3 does not execute confirmable actions."
            )
        return definition
