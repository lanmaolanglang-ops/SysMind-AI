from __future__ import annotations

import ctypes
import os
import time
from threading import Event

import pytest
from fastapi.testclient import TestClient

from sysmind.windows import WindowsNetworkProbe, WindowsServiceProbe, WindowsStartupProbe
from sysmind.windows.platform_inspection import _icmp_reply_succeeded


def test_icmp_reply_status_must_be_success() -> None:
    success = ctypes.create_string_buffer(32)
    failure = ctypes.create_string_buffer(32)
    failure[4:8] = (11010).to_bytes(4, "little")

    assert _icmp_reply_succeeded(success)
    assert not _icmp_reply_succeeded(failure)


@pytest.mark.windows_smoke
@pytest.mark.skipif(os.name != "nt", reason="Windows-only read-only adapter smoke")
def test_phase4_windows_read_only_inventory_smoke() -> None:
    proxy = WindowsNetworkProbe().proxy_configuration()
    startup = WindowsStartupProbe().list_items()
    services = WindowsServiceProbe().list_services()

    assert isinstance(proxy.enabled, bool)
    assert len(startup) <= 200
    assert 0 < len(services) <= 500


@pytest.mark.windows_smoke
@pytest.mark.skipif(os.name != "nt", reason="Windows-only bounded network smoke")
def test_phase4_windows_bounded_network_smoke() -> None:
    probe = WindowsNetworkProbe()
    dns = probe.dns_check("one.one.one.one", Event())
    ping = probe.ping("1.1.1.1", 1, 1000, Event())

    assert dns.domain == "one.one.one.one"
    assert dns.duration_ms >= 0
    assert ping.sent == 1
    assert ping.received in {0, 1}


@pytest.mark.windows_smoke
@pytest.mark.skipif(os.name != "nt", reason="Windows-only diagnosis API smoke")
def test_phase4_windows_performance_diagnosis_smoke(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = client.post(
        "/api/v1/diagnoses",
        json={"question": "电脑最近运行很卡"},
        headers=auth_headers,
    ).json()
    for _ in range(300):
        result = client.get(f"/api/v1/diagnoses/{created['id']}", headers=auth_headers).json()
        if result["status"] in {"completed", "partial", "failed"}:
            break
        time.sleep(0.02)
    assert result["status"] in {"completed", "partial"}
    assert result["report"]["findings"]
