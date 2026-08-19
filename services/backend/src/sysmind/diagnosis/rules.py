from __future__ import annotations

import uuid
from typing import cast

from sysmind.domain.diagnosis import (
    DiagnosisCategory,
    DiagnosisToolCall,
    EvidenceReference,
    Finding,
    Severity,
)


def _finding(
    code: str,
    severity: str,
    title: str,
    explanation: str,
    recommendation: str,
    confidence: float,
    call: DiagnosisToolCall,
    path: str,
) -> Finding:
    return Finding(
        id=str(uuid.uuid4()),
        code=code,
        severity=cast(Severity, severity),
        title=title,
        explanation=explanation,
        recommendation=recommendation,
        confidence=confidence,
        evidence=(EvidenceReference(call.id, path),),
    )


def build_findings(
    category: DiagnosisCategory, calls: tuple[DiagnosisToolCall, ...]
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    successful = [call for call in calls if call.status == "completed" and call.result is not None]
    for call in successful:
        result = call.result
        if call.tool_name == "system.cpu" and isinstance(result, dict):
            usage = float(result.get("utilization_percent", 0))
            if usage >= 85:
                findings.append(
                    _finding(
                        "cpu_pressure",
                        "high",
                        "CPU 当前负载很高",
                        f"采样利用率为 {usage:.1f}%。",
                        "关闭非必要高占用应用后复测。",
                        0.9,
                        call,
                        "$.utilization_percent",
                    )
                )
        elif call.tool_name == "system.memory" and isinstance(result, dict):
            usage = float(result.get("utilization_percent", 0))
            if usage >= 85:
                findings.append(
                    _finding(
                        "memory_pressure",
                        "high",
                        "内存压力较高",
                        f"当前内存使用率为 {usage:.1f}%。",
                        "保存工作后关闭非必要应用并观察内存变化。",
                        0.9,
                        call,
                        "$.utilization_percent",
                    )
                )
        elif call.tool_name == "system.disks" and isinstance(result, list):
            for index, disk in enumerate(result):
                if isinstance(disk, dict) and float(disk.get("utilization_percent", 0)) >= 90:
                    findings.append(
                        _finding(
                            "disk_capacity_pressure",
                            "high",
                            "磁盘剩余空间不足",
                            f"卷使用率为 {float(disk['utilization_percent']):.1f}%。",
                            "优先手动检查可安全清理的数据，不自动删除文件。",
                            0.95,
                            call,
                            f"$[{index}].utilization_percent",
                        )
                    )
        elif call.tool_name == "process.high_usage" and isinstance(result, list) and result:
            findings.append(
                _finding(
                    "resource_competition",
                    "medium",
                    "检测到高占用进程",
                    f"短窗口内有 {len(result)} 个进程达到阈值。",
                    "在任务管理器核对进程用途和持续时间；当前报告不会终止进程。",
                    0.78,
                    call,
                    "$",
                )
            )
        elif call.tool_name == "startup.analyze" and isinstance(result, dict):
            count = int(result.get("item_count", 0))
            if count >= 20:
                findings.append(
                    _finding(
                        "large_startup_inventory",
                        "low",
                        "启动项数量较多",
                        f"只读清单包含 {count} 个启动项。",
                        "逐项核对来源；未知项不等于恶意，当前报告不会禁用它们。",
                        0.72,
                        call,
                        "$.item_count",
                    )
                )
        elif call.tool_name == "service.analyze" and isinstance(result, dict):
            count = int(result.get("stopped_automatic_count", 0))
            if count:
                findings.append(
                    _finding(
                        "stopped_automatic_services",
                        "low",
                        "存在未运行的自动服务",
                        f"检测到 {count} 个自动启动但当前未运行的服务。",
                        "结合具体故障和服务用途人工核对，不要批量启动服务。",
                        0.55,
                        call,
                        "$.stopped_automatic_count",
                    )
                )
        elif (
            call.tool_name == "network.proxy.get_config"
            and isinstance(result, dict)
            and result.get("enabled")
        ):
            findings.append(
                _finding(
                    "proxy_enabled",
                    "info",
                    "系统代理已启用",
                    "当前用户代理配置处于启用状态。",
                    "若仅特定网站无法访问，请核对代理用途和配置。",
                    0.85,
                    call,
                    "$.enabled",
                )
            )
        elif call.tool_name == "network.diagnose" and isinstance(result, dict):
            ping = result.get("ping")
            if result.get("has_default_route") is False:
                findings.append(
                    _finding(
                        "no_active_adapter",
                        "high",
                        "未检测到活动网络适配器",
                        "分层检查未发现活动适配器。",
                        "检查飞行模式、网卡状态和物理连接。",
                        0.92,
                        call,
                        "$.has_default_route",
                    )
                )
            if result.get("dns") is None:
                findings.append(
                    _finding(
                        "dns_unavailable",
                        "high",
                        "DNS 测试未完成",
                        "固定测试域名未得到解析结果。",
                        "检查 DNS 服务器配置后重试。",
                        0.82,
                        call,
                        "$.dns",
                    )
                )
            if isinstance(ping, dict) and float(ping.get("loss_percent", 0)) >= 50:
                findings.append(
                    _finding(
                        "network_packet_loss",
                        "high",
                        "固定目标连通性较差",
                        f"受限 ICMP 测试丢包率为 {float(ping['loss_percent']):.1f}%。",
                        "检查本机连接和网关；目标可能禁用 ICMP，因此该证据不能单独定论。",
                        0.7,
                        call,
                        "$.ping.loss_percent",
                    )
                )
        elif call.tool_name == "log.crash.analyze" and isinstance(result, list) and result:
            total = sum(int(item.get("count", 0)) for item in result if isinstance(item, dict))
            findings.append(
                _finding(
                    "application_crashes",
                    "high" if total >= 3 else "medium",
                    "发现应用崩溃记录",
                    f"最近时间窗聚合到 {total} 条崩溃事件。",
                    "按报告中的应用、模块和异常码顺序排查，并先更新或修复对应应用。",
                    0.93,
                    call,
                    "$",
                )
            )
    if not findings and successful:
        call = successful[0]
        findings.append(
            _finding(
                "insufficient_signal",
                "info",
                "未发现达到规则阈值的异常",
                "已完成计划内只读检查，但当前快照没有形成确定性异常结论。",
                "若问题可复现，请在发生时重新诊断并补充具体应用或时间。",
                0.45,
                call,
                "$",
            )
        )
    return tuple(findings)
