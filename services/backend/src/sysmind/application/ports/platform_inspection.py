from __future__ import annotations

from collections.abc import Sequence
from threading import Event
from typing import Protocol

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


class NetworkProbe(Protocol):
    def proxy_configuration(self) -> ProxyConfiguration: ...

    def dns_check(self, domain: str, cancel_event: Event) -> DnsCheckResult: ...

    def ping(self, target: str, count: int, timeout_ms: int, cancel_event: Event) -> PingResult: ...

    def diagnose(self, cancel_event: Event) -> NetworkDiagnosis: ...


class StartupProbe(Protocol):
    def list_items(self) -> Sequence[StartupItem]: ...

    def analyze(self) -> StartupAssessment: ...


class ServiceProbe(Protocol):
    def list_services(self) -> Sequence[ServiceInfo]: ...

    def analyze(self) -> ServiceAssessment: ...
