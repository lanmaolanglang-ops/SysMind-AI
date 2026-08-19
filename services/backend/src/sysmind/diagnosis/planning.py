from __future__ import annotations

from dataclasses import dataclass

from sysmind.domain.diagnosis import DiagnosisCategory


@dataclass(frozen=True, slots=True)
class DiagnosticStep:
    tool: str
    arguments: dict[str, object]
    purpose: str


def classify_question(question: str) -> tuple[DiagnosisCategory, bool]:
    normalized = question.casefold()
    groups: tuple[tuple[DiagnosisCategory, tuple[str, ...]], ...] = (
        ("network", ("网络", "联网", "上网", "dns", "ping", "代理", "network", "internet")),
        ("crash", ("崩溃", "闪退", "报错", "crash", "exception", "停止工作")),
        ("performance", ("卡", "慢", "掉帧", "cpu", "内存", "磁盘", "风扇", "performance")),
    )
    matches = [category for category, words in groups if any(word in normalized for word in words)]
    return (matches[0] if matches else "performance", len(matches) == 1)


def plan_for(category: DiagnosisCategory) -> tuple[DiagnosticStep, ...]:
    if category == "network":
        return (
            DiagnosticStep("network.proxy.get_config@1.0", {}, "读取当前用户代理元数据"),
            DiagnosticStep("network.diagnose@1.0", {}, "执行固定目标的分层网络检查"),
            DiagnosticStep("service.analyze@1.0", {}, "检查网络相关异常是否伴随服务异常"),
        )
    if category == "crash":
        return (
            DiagnosticStep(
                "log.crash.analyze@1.0",
                {
                    "channel": "Application",
                    "lookback_hours": 24,
                    "levels": ["error", "critical"],
                    "event_ids": [1000, 1001],
                    "max_events": 100,
                },
                "聚合最近 24 小时的应用崩溃证据",
            ),
            DiagnosticStep("process.snapshot@1.0", {"limit": 100}, "采集当前进程上下文"),
            DiagnosticStep("service.analyze@1.0", {}, "检查相关系统服务概况"),
        )
    return (
        DiagnosticStep("system.cpu@1.0", {}, "采集 CPU 状态"),
        DiagnosticStep("system.memory@1.0", {}, "采集内存压力"),
        DiagnosticStep("system.disks@1.0", {}, "采集固定卷容量"),
        DiagnosticStep(
            "process.high_usage@1.0",
            {"sample_seconds": 0.5, "cpu_threshold": 25, "memory_threshold": 10, "limit": 20},
            "短窗口识别高占用进程",
        ),
        DiagnosticStep("startup.analyze@1.0", {}, "分析启动项规模"),
        DiagnosticStep("service.analyze@1.0", {}, "分析服务状态"),
    )
