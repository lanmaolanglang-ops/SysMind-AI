from __future__ import annotations

from dataclasses import dataclass


def _require_count_matches(field_name: str, declared: int, derived: int) -> None:
    if declared != derived:
        raise ValueError(f"{field_name} ({declared}) disagrees with the collection ({derived}).")


def _require_subset(field_name: str, declared: int, total: int) -> None:
    if not 0 <= declared <= total:
        raise ValueError(f"{field_name} ({declared}) must be between 0 and {total}.")


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
    has_default_route: bool | None
    dns: DnsCheckResult | None
    ping: PingResult | None
    proxy: ProxyConfiguration
    failures: tuple[str, ...]
    active_adapter_count: int = 0
    default_gateway: str | None = None
    gateway_reachable: bool | None = None
    public_reachable: bool | None = None


@dataclass(frozen=True, slots=True)
class StartupItem:
    name: str
    source: str
    location: str
    command_name: str | None
    publisher: str | None = None
    signature_status: str = "unavailable"
    item_id: str | None = None


@dataclass(frozen=True, slots=True)
class StartupAssessment:
    items: tuple[StartupItem, ...]
    item_count: int
    high_impact_count: int
    observations: tuple[str, ...]
    unknown_signature_count: int

    def __post_init__(self) -> None:
        # The counts are duplicates of what `items` already says. Left unchecked
        # they drift silently, and every consumer trusts whichever field it reads.
        _require_count_matches("item_count", self.item_count, len(self.items))
        _require_subset("high_impact_count", self.high_impact_count, self.item_count)
        _require_subset("unknown_signature_count", self.unknown_signature_count, self.item_count)


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

    def __post_init__(self) -> None:
        _require_count_matches("service_count", self.service_count, len(self.services))
        _require_subset("stopped_automatic_count", self.stopped_automatic_count, self.service_count)
