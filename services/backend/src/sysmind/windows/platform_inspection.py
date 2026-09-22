from __future__ import annotations

import ctypes
import ipaddress
import os
import re
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from ctypes import wintypes
from pathlib import Path
from threading import Event
from typing import Any

import psutil

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
from sysmind.tools.contracts import ToolCancelledError, ToolUnavailableError
from sysmind.windows.identity import startup_item_id

_DNS_DOMAINS = {"one.one.one.one", "www.microsoft.com"}
_PING_TARGETS = {"1.1.1.1", "8.8.8.8"}
_IP_SUCCESS = 0
_MAX_PING_TIMEOUT_MS = 30_000
_MAX_PING_COUNT = 10
# ProxyServer can embed basic credentials ("http://user:pass@host:8080").
_PROXY_CREDENTIALS = re.compile(r"(?i)([^:/@\s]+):([^@/\s]+)@")


def _redact_proxy(value: str | None) -> str | None:
    if not value:
        return value
    return _PROXY_CREDENTIALS.sub("[REDACTED]@", value)


class _WinHttpProxyInfo(ctypes.Structure):
    _fields_ = (
        ("access_type", wintypes.DWORD),
        ("proxy", ctypes.c_void_p),
        ("proxy_bypass", ctypes.c_void_p),
    )


def _winhttp_proxy() -> str | None:
    if os.name != "nt":
        return None
    winhttp = ctypes.WinDLL("winhttp.dll")
    winhttp.WinHttpGetDefaultProxyConfiguration.argtypes = (ctypes.POINTER(_WinHttpProxyInfo),)
    winhttp.WinHttpGetDefaultProxyConfiguration.restype = wintypes.BOOL
    info = _WinHttpProxyInfo()
    if not winhttp.WinHttpGetDefaultProxyConfiguration(ctypes.byref(info)):
        return None
    proxy = ctypes.wstring_at(info.proxy) if info.proxy else None
    kernel32 = ctypes.WinDLL("kernel32.dll")
    kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
    kernel32.GlobalFree.restype = ctypes.c_void_p
    if info.proxy:
        kernel32.GlobalFree(info.proxy)
    if info.proxy_bypass:
        kernel32.GlobalFree(info.proxy_bypass)
    return proxy


def _check_cancel(cancel_event: Event) -> None:
    if cancel_event.is_set():
        raise ToolCancelledError("Tool execution was cancelled.")


# Registry command lines are frequently stored *unquoted* even when the path
# contains spaces, so splitting on the first space truncates
# "C:\Program Files\App\app.exe" down to "C:\Program". Anchoring on the
# executable extension recovers the real path for the common case.
_EXECUTABLE_SUFFIXES = (".exe", ".cmd", ".bat", ".com", ".ps1", ".vbs", ".js", ".wsf")


def _executable_token(text: str) -> str:
    lowered = text.lower()
    for suffix in _EXECUTABLE_SUFFIXES:
        index = lowered.find(suffix)
        if index == -1:
            continue
        end = index + len(suffix)
        if end < len(text) and text[end] not in " \t'\"":
            continue
        if suffix == ".com" and not _com_ends_path_token(text, index):
            continue
        return text[:end]
    parts = text.split()
    return parts[0] if parts else text


def _com_ends_path_token(text: str, index: int) -> bool:
    """True when '.com' ends a filesystem token, not a hostname TLD.

    ``_executable_token`` must recover ``C:\\tools\\command.com`` but must not
    treat the ``.com`` in ``ping example.com`` or ``https://host.com/x`` as an
    executable boundary.
    """
    if index == 0:
        return True
    prefix = text[:index]
    if "://" in prefix or prefix.endswith("//"):
        return False
    token_start = 0
    for position in range(len(prefix) - 1, -1, -1):
        if prefix[position] in " \t'\"":
            token_start = position + 1
            break
    token = text[token_start : index + 4]
    if "\\" in token or "/" in token:
        return True
    # Bare "app.com" as the first whitespace token; "www.example.com" is a host.
    return token_start == 0 and token.count(".") == 1


def _basename(command: str) -> str | None:
    text = command.strip()
    if not text:
        return None
    if text.startswith('"') and '"' in text[1:]:
        executable = text.split('"', 2)[1]
    else:
        executable = _executable_token(text)
    return Path(executable).name or None


def _registry_dns_servers() -> tuple[str, ...]:
    if os.name != "nt":
        return ()
    import winreg

    found: set[str] = set()
    path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as root:
            for index in range(winreg.QueryInfoKey(root)[0]):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, index)) as interface:
                        for name in ("NameServer", "DhcpNameServer"):
                            try:
                                raw, _ = winreg.QueryValueEx(interface, name)
                            except OSError:
                                continue
                            if isinstance(raw, str):
                                found.update(raw.replace(",", " ").split())
                except OSError:
                    # One unreadable interface must not discard the others.
                    continue
    except OSError:
        return ()
    return tuple(sorted(found))[:8]


def _registry_default_gateways() -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Return ``(ipv4_gateways, ipv6_gateways)`` or ``None`` when unreadable.

    Both the IPv4 (`Tcpip`) and IPv6 (`Tcpip6`) interface stores are consulted so
    an IPv6-only default route is not reported as "no route".
    """
    if os.name != "nt":
        return None
    import winreg

    ipv4: set[str] = set()
    ipv6: set[str] = set()
    paths = (
        (r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces", ipv4),
        (r"SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters\Interfaces", ipv6),
    )
    unreadable = 0
    for path, bucket in paths:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, index)) as interface:
                            for name in ("DefaultGateway", "DhcpDefaultGateway"):
                                try:
                                    raw, _ = winreg.QueryValueEx(interface, name)
                                except OSError:
                                    continue
                                values = raw if isinstance(raw, list) else str(raw).split()
                                for value in values:
                                    try:
                                        address = ipaddress.ip_address(str(value).strip())
                                    except ValueError:
                                        continue
                                    if address.is_unspecified:
                                        continue
                                    bucket.add(str(address))
                    except OSError:
                        continue
        except OSError:
            unreadable += 1
    if unreadable == len(paths):
        return None
    return tuple(sorted(ipv4)), tuple(sorted(ipv6))


def _icmp_reply_succeeded(reply: Any) -> bool:
    return int.from_bytes(reply.raw[4:8], "little") == _IP_SUCCESS


class WindowsNetworkProbe:
    def proxy_configuration(self) -> ProxyConfiguration:
        if os.name != "nt":
            raise ToolUnavailableError("Windows proxy inspection is unavailable.")
        import winreg

        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                enabled = bool(winreg.QueryValueEx(key, "ProxyEnable")[0])
                try:
                    server = str(winreg.QueryValueEx(key, "ProxyServer")[0]) or None
                except OSError:
                    server = None
                try:
                    bypass = str(winreg.QueryValueEx(key, "ProxyOverride")[0])
                except OSError:
                    bypass = ""
                try:
                    auto = bool(str(winreg.QueryValueEx(key, "AutoConfigURL")[0]))
                except OSError:
                    auto = False
        except OSError as error:
            raise ToolUnavailableError("Windows proxy configuration is unavailable.") from error
        return ProxyConfiguration(
            enabled,
            _redact_proxy(server),
            len([x for x in bypass.split(";") if x]),
            auto,
            _redact_proxy(_winhttp_proxy()),
        )

    def dns_check(self, domain: str, cancel_event: Event) -> DnsCheckResult:
        if domain not in _DNS_DOMAINS:
            raise ValueError("DNS target is outside the application allowlist.")
        _check_cancel(cancel_event)
        started = time.monotonic()
        try:
            addresses = tuple(sorted({str(item[4][0]) for item in socket.getaddrinfo(domain, 443)}))
        except OSError as error:
            raise ToolUnavailableError("DNS resolution failed.") from error
        _check_cancel(cancel_event)
        return DnsCheckResult(
            domain,
            addresses[:8],
            _registry_dns_servers(),
            round((time.monotonic() - started) * 1000),
        )

    def ping(self, target: str, count: int, timeout_ms: int, cancel_event: Event) -> PingResult:
        if target not in _PING_TARGETS:
            raise ValueError("Ping target is outside the application allowlist.")
        return self._ping_ipv4(target, count, timeout_ms, cancel_event)

    def _ping_ipv4(
        self, target: str, count: int, timeout_ms: int, cancel_event: Event
    ) -> PingResult:
        if os.name != "nt":
            raise ToolUnavailableError("Windows ICMP is unavailable.")
        if count <= 0:
            return PingResult(target, 0, 0, 0.0, None)
        count = min(count, _MAX_PING_COUNT)
        timeout_ms = min(max(int(timeout_ms), 1), _MAX_PING_TIMEOUT_MS)
        iphlpapi = ctypes.WinDLL("iphlpapi.dll")
        ws2_32 = ctypes.WinDLL("ws2_32.dll")
        iphlpapi.IcmpCreateFile.restype = wintypes.HANDLE
        iphlpapi.IcmpSendEcho.restype = wintypes.DWORD
        iphlpapi.IcmpSendEcho.argtypes = (
            wintypes.HANDLE,
            wintypes.ULONG,
            wintypes.LPVOID,
            wintypes.WORD,
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
        )
        iphlpapi.IcmpCloseHandle.argtypes = (wintypes.HANDLE,)
        iphlpapi.IcmpCloseHandle.restype = wintypes.BOOL
        ws2_32.inet_addr.argtypes = (wintypes.LPCSTR,)
        ws2_32.inet_addr.restype = wintypes.ULONG
        handle = iphlpapi.IcmpCreateFile()
        # INVALID_HANDLE_VALUE is (HANDLE)-1, which is pointer-sized: on 64-bit
        # Python ctypes may surface 0xFFFFFFFFFFFFFFFF rather than -1.
        invalid_handle = ctypes.c_void_p(-1).value
        if handle is None or int(handle) in (0, -1, 0xFFFFFFFF, invalid_handle):
            raise ToolUnavailableError("Windows could not open an ICMP handle.")
        payload = b"sysmind"
        durations: list[int] = []
        try:
            for _ in range(count):
                _check_cancel(cancel_event)
                reply = ctypes.create_string_buffer(256)
                result = iphlpapi.IcmpSendEcho(
                    handle,
                    ws2_32.inet_addr(target.encode("ascii")),
                    payload,
                    len(payload),
                    None,
                    reply,
                    len(reply),
                    timeout_ms,
                )
                if result and _icmp_reply_succeeded(reply):
                    durations.append(int.from_bytes(reply.raw[8:12], "little"))
        finally:
            iphlpapi.IcmpCloseHandle(handle)
        return PingResult(
            target,
            count,
            len(durations),
            round((count - len(durations)) * 100 / count, 1),
            round(sum(durations) / len(durations), 1) if durations else None,
        )

    def diagnose(self, cancel_event: Event) -> NetworkDiagnosis:
        failures: list[str] = []
        proxy = self.proxy_configuration()
        dns: DnsCheckResult | None = None
        ping: PingResult | None = None
        try:
            dns = self.dns_check("one.one.one.one", cancel_event)
        except ToolUnavailableError:
            failures.append("dns_unavailable")
        try:
            ping = self.ping("1.1.1.1", 2, 1000, cancel_event)
        except ToolUnavailableError:
            failures.append("icmp_unavailable")
        adapters = [name for name, values in psutil.net_if_addrs().items() if values]
        stats = psutil.net_if_stats()
        active_adapters = [name for name in adapters if stats.get(name) and stats[name].isup]
        gateways = _registry_default_gateways()
        ipv4_gateways: tuple[str, ...] = ()
        ipv6_gateways: tuple[str, ...] = ()
        if gateways is None:
            failures.append("default_route_unavailable")
        else:
            ipv4_gateways, ipv6_gateways = gateways
        gateway = (
            ipv4_gateways[0]
            if ipv4_gateways
            else (ipv6_gateways[0] if ipv6_gateways else None)
        )
        gateway_ipv6 = ipv6_gateways[0] if ipv6_gateways else None
        gateway_reachable: bool | None = None
        if gateway is not None and ":" not in gateway:
            # ICMP echo here is IPv4-only; an IPv6 gateway must not be probed with it.
            try:
                gateway_reachable = (
                    self._ping_ipv4(gateway, 2, 750, cancel_event).received > 0
                )
            except ToolUnavailableError:
                failures.append("gateway_icmp_unavailable")
        elif gateway is not None:
            # IPv6 gateway present but not ICMP-probed: stay unknown rather than
            # claiming reachability or failure from an unmeasured fact.
            gateway_reachable = None
        measured = gateways is not None
        has_ipv4_route = bool(ipv4_gateways) if measured and active_adapters else (
            False if measured and not active_adapters else None
        )
        has_ipv6_route = bool(ipv6_gateways) if measured and active_adapters else (
            False if measured and not active_adapters else None
        )
        if has_ipv4_route is True or has_ipv6_route is True:
            has_default_route: bool | None = True
        elif has_ipv4_route is False and has_ipv6_route is False:
            has_default_route = False
        else:
            has_default_route = None
        return NetworkDiagnosis(
            len(adapters),
            has_default_route,
            dns,
            ping,
            proxy,
            tuple(failures),
            len(active_adapters),
            gateway,
            gateway_reachable,
            ping.received > 0 if ping is not None else None,
            default_gateway_ipv6=gateway_ipv6,
            has_default_route_ipv4=has_ipv4_route,
            has_default_route_ipv6=has_ipv6_route,
        )


def _scheduled_startup_task_paths() -> set[str] | None:
    """Return Task Scheduler paths that are enabled startup (boot/logon) tasks.

    Uses the system ``schtasks /Query /XML ONE`` collector (read-only, fixed argv).
    Returns ``None`` when the collector is unavailable so callers fail closed and
    do not promote every scheduled task into the startup inventory.
    """
    if os.name != "nt":
        return None
    try:
        completed = subprocess.run(
            ["schtasks", "/Query", "/XML", "ONE"],
            capture_output=True,
            timeout=8,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        root = ET.fromstring(completed.stdout.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return None
    startup_tags = {"BootTrigger", "LogonTrigger", "SessionStateChangeTrigger"}
    paths: set[str] = set()
    for task in root.findall(".//Task"):
        # Disabled tasks must not count as startup entries.
        settings = task.find("Settings")
        if settings is not None:
            enabled = settings.findtext("Enabled")
            if enabled is not None and enabled.strip().lower() == "false":
                continue
        registration = task.find("RegistrationInfo")
        # schtasks XML uses URI-style Task elements; prefer the parent path text.
        path_text = (registration.findtext("URI") if registration is not None else None) or ""
        triggers = task.find("Triggers")
        if triggers is None:
            continue
        kinds = {child.tag.split("}")[-1] for child in list(triggers)}
        if kinds & startup_tags:
            paths.add(path_text.strip())
    return paths


class WindowsStartupProbe:
    def list_items(self) -> tuple[StartupItem, ...]:
        if os.name != "nt":
            raise ToolUnavailableError("Windows startup inspection is unavailable.")
        import winreg

        items: list[StartupItem] = []
        keys = (
            (
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                "user_run",
            ),
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                "machine_run",
            ),
        )
        for hive, path, source in keys:
            try:
                with winreg.OpenKey(hive, path) as key:
                    for index in range(min(winreg.QueryInfoKey(key)[1], 100)):
                        name, value, _ = winreg.EnumValue(key, index)
                        items.append(
                            StartupItem(
                                name,
                                source,
                                source,
                                _basename(str(value)),
                                item_id=startup_item_id(source, name),
                            )
                        )
            except (OSError, PermissionError):
                continue
        for root, source in (
            (os.environ.get("APPDATA"), "user_startup"),
            (os.environ.get("PROGRAMDATA"), "common_startup"),
        ):
            if not root:
                continue
            folder = Path(root) / "Microsoft/Windows/Start Menu/Programs/Startup"
            try:
                for entry in list(folder.iterdir())[:100]:
                    try:
                        attributes = entry.lstat().st_file_attributes
                    except (AttributeError, OSError):
                        attributes = 0
                    if (
                        not entry.is_file()
                        or entry.is_symlink()
                        or attributes & 0x400
                    ):
                        continue
                    items.append(
                        StartupItem(
                            entry.stem,
                            source,
                            source,
                            entry.name,
                            item_id=startup_item_id(source, entry.stem),
                        )
                    )
            except OSError:
                continue
        task_cache = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tree"
        # Only boot/logon/startup-triggered, enabled tasks count as startup items.
        # Unknown-trigger tasks are omitted (unknown ≠ safe), not silently included.
        startup_task_paths = _scheduled_startup_task_paths()
        trigger_unknown = 0

        def scheduled_tasks(key: Any, prefix: str = "", depth: int = 0) -> None:
            nonlocal trigger_unknown
            if depth > 4 or len(items) >= 200:
                return
            try:
                count = winreg.QueryInfoKey(key)[0]
            except OSError:
                return
            for index in range(min(count, 100)):
                try:
                    name = winreg.EnumKey(key, index)
                    path = f"{prefix}\\{name}" if prefix else name
                    with winreg.OpenKey(key, name) as child:
                        try:
                            # Only real task leaves carry an Id; folder nodes in the
                            # Tree hierarchy must not be reported as startup items.
                            winreg.QueryValueEx(child, "Id")
                        except OSError:
                            scheduled_tasks(child, path, depth + 1)
                            continue
                        if startup_task_paths is None:
                            trigger_unknown += 1
                        elif (
                            path not in startup_task_paths
                            and f"\\{path}" not in startup_task_paths
                        ):
                            # Non-startup trigger (or disabled) — not a startup item.
                            scheduled_tasks(child, path, depth + 1)
                            continue
                        items.append(
                            StartupItem(
                                path,
                                "scheduled_task",
                                "task_scheduler",
                                None,
                                item_id=startup_item_id("scheduled_task", path),
                            )
                        )
                        scheduled_tasks(child, path, depth + 1)
                except OSError:
                    continue

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, task_cache) as tasks:
                scheduled_tasks(tasks)
        except (OSError, PermissionError):
            pass
        return tuple(items[:200])

    def analyze(self) -> StartupAssessment:
        items = self.list_items()
        observations = (
            (
                "Startup inventory is large."
                if len(items) >= 20
                else "Startup inventory is bounded."
            ),
            "High-impact startup entries require workload context and are not inferred here.",
            "Unknown publisher or path is not treated as malicious.",
        )
        # Trigger-unknown scheduled tasks are omitted from the inventory rather
        # than counted as startup items.
        return StartupAssessment(
            items,
            len(items),
            0,
            observations,
            0,
        )


class WindowsServiceProbe:
    def list_services(self) -> tuple[ServiceInfo, ...]:
        if os.name != "nt" or not hasattr(psutil, "win_service_iter"):
            raise ToolUnavailableError("Windows service inspection is unavailable.")
        services: list[ServiceInfo] = []
        try:
            for service in psutil.win_service_iter():
                try:
                    data = service.as_dict()
                    services.append(
                        ServiceInfo(
                            str(data.get("name", "")),
                            str(data.get("display_name", "")),
                            str(data.get("status", "unknown")),
                            str(data.get("start_type", "unknown")),
                            str(data.get("username")) if data.get("username") else None,
                            _basename(str(data.get("binpath", ""))),
                        )
                    )
                except (OSError, psutil.Error):
                    continue
        except (OSError, psutil.Error) as error:
            raise ToolUnavailableError("Windows service inventory is unavailable.") from error
        return tuple(services[:500])

    def analyze(self) -> ServiceAssessment:
        services = self.list_services()
        # Paused services are still started, and trigger-start services are not
        # plain boot-automatic; neither is a "stopped automatic" finding.
        stopped = sum(
            1
            for item in services
            if item.start_type in {"automatic", "automatic (delayed start)"}
            and "trigger" not in item.start_type.casefold()
            and item.status == "stopped"
        )
        return ServiceAssessment(
            services,
            len(services),
            stopped,
            ("Stopped automatic services require workload context before classification.",),
        )
