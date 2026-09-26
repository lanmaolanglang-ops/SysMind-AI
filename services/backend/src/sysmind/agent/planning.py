from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, Protocol, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sysmind.agent.context import AgentContextBuilder
from sysmind.agent.contracts import AgentProvider
from sysmind.domain.diagnosis import DiagnosisToolCall
from sysmind.tools.registry import ToolRegistry

ProblemCategory: TypeAlias = Literal["performance", "network", "crash"]
PlanStatus: TypeAlias = Literal["ready", "ask_user", "complete"]

MAX_PLAN_STEPS = 8


def remaining_plan_budget(calls: tuple[DiagnosisToolCall, ...]) -> int:
    """How many further steps a revision may add.

    Clamped at 0 so a diagnosis that already exceeded its budget tightens
    instead of loosening: both planners must agree on this, otherwise a
    provider-driven revision can silently accept steps the fake planner
    would reject.
    """
    return max(0, MAX_PLAN_STEPS - len(calls))


@dataclass(frozen=True, slots=True)
class DiagnosisPlanStep:
    tool: str
    reason: str
    arguments: dict[str, object]


@dataclass(frozen=True, slots=True)
class DiagnosisPlan:
    problem_category: ProblemCategory
    confidence: float
    steps: tuple[DiagnosisPlanStep, ...]
    status: PlanStatus = "ready"
    clarification_question: str | None = None

    def as_dict(self) -> dict[str, object]:
        return cast(dict[str, object], asdict(self))


class PlanStepPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = Field(min_length=5, max_length=110)
    reason: str = Field(min_length=3, max_length=300)
    arguments: dict[str, object] = Field(default_factory=dict)


class PlanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_category: ProblemCategory
    confidence: float = Field(ge=0, le=1)
    status: PlanStatus = "ready"
    clarification_question: str | None = Field(default=None, min_length=3, max_length=500)
    steps: tuple[PlanStepPayload, ...] = Field(default=(), max_length=8)


class DiagnosisPlannerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DiagnosisPlanner(Protocol):
    @property
    def name(self) -> str: ...

    async def create_plan(self, question: str) -> DiagnosisPlan: ...

    async def revise_plan(
        self,
        question: str,
        plan: DiagnosisPlan,
        calls: tuple[DiagnosisToolCall, ...],
    ) -> DiagnosisPlan | None: ...


def validate_plan(
    payload: PlanPayload,
    registry: ToolRegistry,
    *,
    max_steps: int = MAX_PLAN_STEPS,
    already_called: tuple[str, ...] = (),
) -> DiagnosisPlan:
    if payload.status == "ask_user":
        if not payload.clarification_question or payload.steps:
            raise DiagnosisPlannerError(
                "invalid_plan", "A clarification plan must contain one question and no tools."
            )
    elif payload.status == "ready" and not payload.steps:
        raise DiagnosisPlannerError("invalid_plan", "A ready plan must contain at least one step.")
    if len(payload.steps) > max_steps:
        raise DiagnosisPlannerError(
            "plan_budget_exceeded", "The diagnosis plan exceeds its budget."
        )

    # ``already_called`` lists tools that already completed successfully. Re-proposing
    # one is not a plan error: keep the step so the coordinator can mark it
    # ``skipped_duplicate``. Failed tools are absent from ``already_called`` and may be
    # retried. Only a repeat within this same plan is a hard duplicate.
    seen_in_plan: set[str] = set()
    validated_steps: list[DiagnosisPlanStep] = []
    for step in payload.steps:
        try:
            definition = registry.require(step.tool)
        except ValueError as error:
            raise DiagnosisPlannerError(
                "unknown_tool", "The plan requested an unknown tool."
            ) from error
        if definition.risk_level not in {"read_only", "network"}:
            raise DiagnosisPlannerError(
                "tool_scope_rejected", "The plan requested a system-changing tool."
            )
        if definition.required_privilege != "user" or definition.confirmation_policy != "none":
            raise DiagnosisPlannerError(
                "tool_scope_rejected", "The plan requested an unauthorized tool."
            )
        if payload.problem_category != "network" and definition.risk_level == "network":
            raise DiagnosisPlannerError(
                "tool_scope_rejected", "Network tools are limited to network diagnoses."
            )
        try:
            normalized = definition.input_model.model_validate(step.arguments).model_dump(
                mode="json"
            )
        except ValidationError as error:
            raise DiagnosisPlannerError(
                "invalid_arguments", "A plan step has arguments outside its registered schema."
            ) from error
        if step.tool in seen_in_plan:
            raise DiagnosisPlannerError(
                "duplicate_tool", "The plan repeated an existing tool call."
            )
        seen_in_plan.add(step.tool)
        validated_steps.append(DiagnosisPlanStep(step.tool, step.reason, normalized))
    return DiagnosisPlan(
        payload.problem_category,
        payload.confidence,
        tuple(validated_steps),
        payload.status,
        payload.clarification_question,
    )


class FakeDiagnosisPlanner:
    """Deterministic offline planner used when no cloud Provider is configured."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "fake-planner"

    async def create_plan(self, question: str) -> DiagnosisPlan:
        normalized = question.casefold().strip()
        insufficient_phrases = (
            "不知道哪里有问题",
            "说不清楚",
            "没有具体症状",
            "帮我看看电脑",
            "电脑有问题",
            "电脑不正常",
        )
        if any(phrase in normalized for phrase in insufficient_phrases):
            return DiagnosisPlan(
                "performance",
                0.2,
                (),
                "ask_user",
                "请说明具体症状、发生场景和大致时间，例如开机后卡顿、无法上网或某个软件闪退。",
            )
        if any(
            word in normalized
            for word in (
                "网络",
                "联网",
                "上网",
                "断网",
                "外网",
                "dns",
                "ping",
                "代理",
                "网关",
                "wifi",
                "wi-fi",
                "internet",
                "ipv6",
                "ipv4",
                "网速",
                "打不开网页",
                "连不上",
            )
        ):
            payload = PlanPayload(
                problem_category="network",
                confidence=0.9,
                steps=(
                    PlanStepPayload(tool="network.proxy.get_config@1.0", reason="检查代理配置"),
                    PlanStepPayload(tool="network.diagnose@1.0", reason="执行受限的分层网络检查"),
                ),
            )
        elif any(word in normalized for word in ("崩溃", "闪退", "crash", "exception", "报错")):
            payload = PlanPayload(
                problem_category="crash",
                confidence=0.92,
                steps=(
                    PlanStepPayload(
                        tool="log.crash.analyze@1.0",
                        reason="关联近期应用崩溃事件",
                        arguments={
                            "channel": "Application",
                            "lookback_hours": 24,
                            "levels": ["error", "critical"],
                            "event_ids": [1000, 1001],
                            "max_events": 100,
                        },
                    ),
                    PlanStepPayload(
                        tool="process.snapshot@1.0",
                        reason="补充当前应用进程上下文",
                        arguments={"limit": 100},
                    ),
                ),
            )
        else:
            steps = [
                PlanStepPayload(tool="system.cpu@1.0", reason="检查当前 CPU 压力"),
                PlanStepPayload(tool="system.memory@1.0", reason="检查当前内存压力"),
                PlanStepPayload(tool="system.disks@1.0", reason="检查磁盘容量压力"),
            ]
            if any(word in normalized for word in ("游戏", "掉帧", "gpu", "显卡")):
                steps.append(PlanStepPayload(tool="system.gpu@1.0", reason="检查显卡与驱动能力"))
            payload = PlanPayload(
                problem_category="performance", confidence=0.86, steps=tuple(steps)
            )
        return validate_plan(payload, self._registry)

    async def revise_plan(
        self,
        question: str,
        plan: DiagnosisPlan,
        calls: tuple[DiagnosisToolCall, ...],
    ) -> DiagnosisPlan | None:
        if plan.problem_category != "performance" or not calls:
            return None
        called = {f"{call.tool_name}@{call.tool_version}" for call in calls}
        next_steps: list[PlanStepPayload] = []
        if "process.high_usage@1.0" not in called:
            next_steps.append(
                PlanStepPayload(
                    tool="process.high_usage@1.0",
                    reason="基础资源结果需要关联到具体高占用进程",
                    arguments={
                        "sample_seconds": 0.5,
                        "cpu_threshold": 25,
                        "memory_threshold": 10,
                        "limit": 20,
                    },
                )
            )
        if (
            any(word in question.casefold() for word in ("开机", "启动"))
            and "startup.analyze@1.0" not in called
        ):
            next_steps.append(
                PlanStepPayload(tool="startup.analyze@1.0", reason="问题发生在开机阶段")
            )
        if not next_steps:
            return None
        # Only successfully completed tools block a retry; failed ones may be re-run.
        signatures = tuple(
            f"{call.tool_name}@{call.tool_version}"
            for call in calls
            if call.status == "completed"
        )
        return validate_plan(
            PlanPayload(
                problem_category="performance",
                confidence=plan.confidence,
                steps=tuple(next_steps),
            ),
            self._registry,
            max_steps=remaining_plan_budget(calls),
            already_called=signatures,
        )


class ProviderDiagnosisPlanner:
    def __init__(
        self,
        registry: ToolRegistry,
        provider: AgentProvider,
        context_builder: AgentContextBuilder | None = None,
    ) -> None:
        self._registry = registry
        self._provider = provider
        self._context_builder = context_builder or AgentContextBuilder()

    @property
    def name(self) -> str:
        return self._provider.name

    async def create_plan(self, question: str) -> DiagnosisPlan:
        request = self._context_builder.build_planning_request(
            question=question,
            tools=tuple(item.descriptor() for item in self._registry.available()),
        )
        try:
            response = await self._provider.complete(request)
        except DiagnosisPlannerError:
            raise
        except Exception as error:
            raise DiagnosisPlannerError(
                "provider_error",
                "Planner provider request failed.",
            ) from error
        return self._parse(response.action.content)

    async def revise_plan(
        self,
        question: str,
        plan: DiagnosisPlan,
        calls: tuple[DiagnosisToolCall, ...],
    ) -> DiagnosisPlan | None:
        request = self._context_builder.build_revision_request(
            question=question,
            tools=tuple(item.descriptor() for item in self._registry.available()),
            current_plan=plan.as_dict(),
            observations=tuple(
                {
                    "tool_call_id": call.id,
                    "tool": f"{call.tool_name}@{call.tool_version}",
                    "status": call.status,
                    "summary": call.summary or {},
                    "error_code": call.error_code,
                }
                for call in calls
            ),
        )
        try:
            response = await self._provider.complete(request)
        except DiagnosisPlannerError:
            raise
        except Exception as error:
            raise DiagnosisPlannerError(
                "provider_error",
                "Planner provider request failed.",
            ) from error
        if response.action.type == "finalize" and response.action.content == "no_revision":
            return None
        # Only successfully completed tools block a retry; failed ones may be re-run.
        called = tuple(
            f"{call.tool_name}@{call.tool_version}"
            for call in calls
            if call.status == "completed"
        )
        return self._parse(
            response.action.content,
            already_called=called,
            max_steps=remaining_plan_budget(calls),
        )

    def _parse(
        self,
        content: str | None,
        *,
        already_called: tuple[str, ...] = (),
        max_steps: int = MAX_PLAN_STEPS,
    ) -> DiagnosisPlan:
        if not content:
            raise DiagnosisPlannerError("provider_protocol_error", "Planner returned no plan.")
        try:
            payload = PlanPayload.model_validate_json(content)
        except ValidationError as error:
            raise DiagnosisPlannerError(
                "provider_protocol_error", "Planner returned an invalid structured plan."
            ) from error
        return validate_plan(
            payload, self._registry, max_steps=max_steps, already_called=already_called
        )
