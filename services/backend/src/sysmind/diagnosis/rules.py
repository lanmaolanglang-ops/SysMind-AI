from __future__ import annotations

import uuid
from typing import cast

from sysmind.domain.diagnosis import (
    DiagnosisCategory,
    DiagnosisToolCall,
    EvidenceReference,
    Finding,
    Severity,
    diagnostic_findings,
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
        elif call.tool_name == "system.gpu" and isinstance(result, list) and result:
            findings.append(
                _finding(
                    "gpu_metadata_only",
                    "info",
                    "GPU 实时负载当前不可用",
                    "已读取显卡与驱动元数据，但当前适配器没有可靠的实时利用率或显存压力。",
                    "如问题涉及掉帧，请结合厂商监控工具复测；本报告不会从元数据推测负载。",
                    0.98,
                    call,
                    "$",
                )
            )
        elif call.tool_name == "network.diagnose" and isinstance(result, dict):
            ping = result.get("ping")
            failures = {
                str(item)
                for item in cast(list[object] | tuple[object, ...], result.get("failures", ()))
            }
            public_reachable = result.get("public_reachable")
            active_adapter_count = result.get("active_adapter_count")
            active_adapter_path: str | None = None
            if active_adapter_count is not None:
                active_adapter_path = "$.active_adapter_count"
            if active_adapter_count is None:
                active_adapter_count = result.get("adapter_count")
                if active_adapter_count is not None:
                    active_adapter_path = "$.adapter_count"
            if (
                active_adapter_count is not None
                and active_adapter_path is not None
                and int(cast(int | str, active_adapter_count)) == 0
            ):
                findings.append(
                    _finding(
                        "no_active_adapter",
                        "high",
                        "未检测到活动网络适配器",
                        "分层检查未发现活动适配器。",
                        "检查飞行模式、网卡状态和物理连接。",
                        0.92,
                        call,
                        active_adapter_path,
                    )
                )
            elif result.get("has_default_route") is False:
                findings.append(
                    _finding(
                        "no_default_route",
                        "high",
                        "未检测到默认路由",
                        "存在活动网络适配器，但未发现可用的默认网关配置。",
                        "检查 IP 与默认网关配置，或重新连接当前网络。",
                        0.9,
                        call,
                        "$.has_default_route",
                    )
                )
            elif result.get("gateway_reachable") is False and public_reachable is not True:
                findings.append(
                    _finding(
                        "gateway_unreachable",
                        "medium",
                        "默认网关 ICMP 未响应",
                        (
                            "已发现默认路由，但受限 ICMP 检查未收到成功状态回复；"
                            "该结果不是网关故障的充分证据。"
                        ),
                        "检查本机链路、无线连接或路由器状态；网关也可能禁用 ICMP。",
                        0.65,
                        call,
                        "$.gateway_reachable",
                    )
                )
            elif result.get("gateway_reachable") is False and public_reachable is True:
                findings.append(
                    Finding(
                        id=str(uuid.uuid4()),
                        code="gateway_icmp_no_response",
                        severity="info",
                        title="默认网关未响应 ICMP，但公网目标可达",
                        explanation=(
                            "公网固定目标已响应，因此网关 ICMP 无响应不能证明本地链路故障。"
                        ),
                        recommendation="无需仅因该结果重置网络；网关可能禁用 ICMP。",
                        confidence=0.96,
                        evidence=(
                            EvidenceReference(call.id, "$.gateway_reachable"),
                            EvidenceReference(call.id, "$.public_reachable"),
                        ),
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
                        "$.failures" if "dns_unavailable" in failures else "$.dns",
                    )
                )
                if result.get("gateway_reachable") is True or public_reachable is True:
                    connectivity_path = (
                        "$.gateway_reachable"
                        if result.get("gateway_reachable") is True
                        else "$.public_reachable"
                    )
                    findings.append(
                        Finding(
                            id=str(uuid.uuid4()),
                            code="dns_failure_after_gateway_success",
                            severity="high",
                            title="本地链路可达但 DNS 解析失败",
                            explanation=(
                                "网络 IP 连通性检查成功，而固定域名解析未完成，故障更接近 DNS 层。"
                            ),
                            recommendation=(
                                "核对网卡 DNS 服务器配置，并尝试受信任的备用 DNS 后复测。"
                            ),
                            confidence=0.88,
                            evidence=(
                                EvidenceReference(call.id, connectivity_path),
                                EvidenceReference(call.id, "$.dns"),
                            ),
                        )
                    )
            capability_messages = {
                "default_route_unavailable": (
                    "默认路由读取能力受限",
                    "系统未能读取默认路由配置，不能据此判断设备确实没有默认路由。",
                ),
                "gateway_icmp_unavailable": (
                    "网关 ICMP 探测不可用",
                    "当前环境无法执行网关 ICMP 探测，网关可达性证据不完整。",
                ),
                "icmp_unavailable": (
                    "公网 ICMP 探测不可用",
                    "当前环境无法执行固定公网目标 ICMP 探测，外网可达性证据不完整。",
                ),
            }
            for failure in sorted(failures & capability_messages.keys()):
                title, explanation = capability_messages[failure]
                findings.append(
                    _finding(
                        f"network_capability_{failure}",
                        "info",
                        title,
                        explanation,
                        "结合其他成功探针判断；如需确认，请在网络稳定时重新诊断。",
                        0.99,
                        call,
                        "$.failures",
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
    if not diagnostic_findings(tuple(findings)) and successful:
        call = successful[0]
        findings.append(
            _finding(
                "insufficient_signal",
                "info",
                "未发现达到规则阈值的异常",
                "当前证据不足，无法确定原因。已完成的只读检查没有形成确定性异常结论。",
                "若问题可复现，请在发生时重新诊断并补充具体应用或时间。",
                0.45,
                call,
                "$",
            )
        )
    return tuple(findings)
