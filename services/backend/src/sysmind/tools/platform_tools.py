from __future__ import annotations

from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from sysmind.application.ports.platform_inspection import NetworkProbe, ServiceProbe, StartupProbe
from sysmind.domain.platform_inspection import (
    DnsCheckResult,
    NetworkDiagnosis,
    PingResult,
    ProxyConfiguration,
    ServiceAssessment,
    ServiceInfo,
    StartupAssessment,
    StartupItem,
)
from sysmind.tools.registry import ToolDefinition


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DnsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: Literal["one.one.one.one", "www.microsoft.com"] = "one.one.one.one"


class PingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["1.1.1.1", "8.8.8.8"] = "1.1.1.1"
    count: int = Field(default=2, ge=1, le=4)
    timeout_ms: int = Field(default=1000, ge=250, le=2000)


def _dict_summary(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _bounded_items(value: object) -> dict[str, object]:
    items = cast(list[object], value)
    return {"item_count": len(items), "items": items[:10]}


def _assessment_summary(value: object) -> dict[str, object]:
    data = cast(dict[str, object], value)
    return {key: val for key, val in data.items() if key != "items" and key != "services"}


def _proxy_summary(value: object) -> dict[str, object]:
    data = cast(dict[str, object], value)
    return {
        "enabled": data.get("enabled"),
        "auto_configured": data.get("auto_configured"),
        "bypass_count": data.get("bypass_count"),
        "winhttp_configured": bool(data.get("winhttp_server")),
    }


def platform_tool_definitions(
    network: NetworkProbe | None,
    startup: StartupProbe | None,
    services: ServiceProbe | None,
) -> tuple[ToolDefinition, ...]:
    definitions: list[ToolDefinition] = []
    if network is not None:
        definitions.extend(
            (
                ToolDefinition(
                    "network.proxy.get_config",
                    "1.0",
                    "Read current-user Windows proxy metadata. Does not change network settings.",
                    NoArguments,
                    TypeAdapter(ProxyConfiguration),
                    "read_only",
                    "user",
                    ("network",),
                    3.0,
                    "network",
                    "none",
                    lambda _args, _cancel: network.proxy_configuration(),
                    _proxy_summary,
                ),
                ToolDefinition(
                    "network.dns.check",
                    "1.0",
                    "Resolve one application-allowlisted public test domain. "
                    "Produces network traffic.",
                    DnsInput,
                    TypeAdapter(DnsCheckResult),
                    "network",
                    "user",
                    ("network", "ip"),
                    5.0,
                    "network",
                    "none",
                    lambda args, cancel: network.dns_check(cast(DnsInput, args).domain, cancel),
                    _dict_summary,
                ),
                ToolDefinition(
                    "network.ping",
                    "1.0",
                    "Send at most four ICMP probes to an application-allowlisted public target.",
                    PingInput,
                    TypeAdapter(PingResult),
                    "network",
                    "user",
                    ("network", "ip"),
                    10.0,
                    "network",
                    "none",
                    lambda args, cancel: network.ping(
                        cast(PingInput, args).target,
                        cast(PingInput, args).count,
                        cast(PingInput, args).timeout_ms,
                        cancel,
                    ),
                    _dict_summary,
                ),
                ToolDefinition(
                    "network.diagnose",
                    "1.0",
                    "Run a fixed adapter, route, DNS, proxy, and allowlisted ICMP diagnostic flow.",
                    NoArguments,
                    TypeAdapter(NetworkDiagnosis),
                    "network",
                    "user",
                    ("network", "ip"),
                    12.0,
                    "network",
                    "none",
                    lambda _args, cancel: network.diagnose(cancel),
                    _dict_summary,
                ),
            )
        )
    if startup is not None:
        definitions.extend(
            (
                ToolDefinition(
                    "startup.list",
                    "1.0",
                    "Read bounded Run-key and Startup-folder metadata; "
                    "never changes startup entries.",
                    NoArguments,
                    TypeAdapter(tuple[StartupItem, ...]),
                    "read_only",
                    "user",
                    ("path", "startup"),
                    8.0,
                    "startup",
                    "none",
                    lambda _args, _cancel: startup.list_items(),
                    _bounded_items,
                ),
                ToolDefinition(
                    "startup.analyze",
                    "1.0",
                    "Apply local bounded startup inventory rules; unknown does not mean malicious.",
                    NoArguments,
                    TypeAdapter(StartupAssessment),
                    "read_only",
                    "user",
                    ("path", "startup"),
                    8.0,
                    "startup",
                    "none",
                    lambda _args, _cancel: startup.analyze(),
                    _assessment_summary,
                ),
            )
        )
    if services is not None:
        definitions.extend(
            (
                ToolDefinition(
                    "service.list",
                    "1.0",
                    "Read a bounded Windows service inventory. Cannot start or stop services.",
                    NoArguments,
                    TypeAdapter(tuple[ServiceInfo, ...]),
                    "read_only",
                    "user",
                    ("path", "account", "service"),
                    10.0,
                    "service",
                    "none",
                    lambda _args, _cancel: services.list_services(),
                    _bounded_items,
                ),
                ToolDefinition(
                    "service.analyze",
                    "1.0",
                    "Apply conservative local rules to service metadata "
                    "without changing service state.",
                    NoArguments,
                    TypeAdapter(ServiceAssessment),
                    "read_only",
                    "user",
                    ("path", "account", "service"),
                    10.0,
                    "service",
                    "none",
                    lambda _args, _cancel: services.analyze(),
                    _assessment_summary,
                ),
            )
        )
    return tuple(definitions)
