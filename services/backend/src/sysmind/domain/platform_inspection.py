from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProxyConfiguration:
    enabled: bool
    server: str | None
    bypass_count: int
    auto_configured: bool
    winhttp_server: str | None


@dataclass(frozen=True, slots=True)
class DnsCheckResult:
    domain: str
    addresses: tuple[str, ...]
    dns_servers: tuple[str, ...]
    duration_ms: int


@dataclass(frozen=True, slots=True)
class PingResult:
    target: str
    sent: int
    received: int
    loss_percent: float
    average_ms: float | None


@dataclass(frozen=True, slots=True)
class NetworkDiagnosis:
    adapter_count: int
    has_default_route: bool
    dns: DnsCheckResult | None
    ping: PingResult | None
    proxy: ProxyConfiguration
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StartupItem:
    name: str
    source: str
    location: str
    command_name: str | None
    publisher: str | None = None
    signature_status: str = "unavailable"


@dataclass(frozen=True, slots=True)
class StartupAssessment:
    items: tuple[StartupItem, ...]
    item_count: int
    high_impact_count: int
    observations: tuple[str, ...]
    unknown_signature_count: int


@dataclass(frozen=True, slots=True)
class ServiceInfo:
    name: str
    display_name: str
    status: str
    start_type: str
    account: str | None
    binary_name: str | None


@dataclass(frozen=True, slots=True)
class ServiceAssessment:
    services: tuple[ServiceInfo, ...]
    service_count: int
    stopped_automatic_count: int
    observations: tuple[str, ...]
