from __future__ import annotations

import ctypes
import ntpath
import re
import sys
import time
from collections.abc import Sequence
from ctypes import wintypes
from datetime import UTC, datetime
from threading import Event
from typing import Any, cast
from xml.etree import ElementTree

from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from defusedxml.ElementTree import fromstring as _safe_fromstring  # type: ignore[import-untyped]

from sysmind.domain.event_logs import EventLevel, EventLogQuery, LogChannel, WindowsEvent
from sysmind.security.redaction import redact_text
from sysmind.tools.contracts import (
    ToolCancelledError,
    ToolPermissionError,
    ToolUnavailableError,
)


def _event_time(value: str) -> datetime:
    """Parse an event timestamp for ordering, tolerating unusual producer formats.

    Lexicographic ordering of ISO-8601 strings is wrong when offsets or fractional-second
    precision differ, so events are ordered by the parsed instant instead. Unparseable
    values sort to the beginning rather than raising.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


_LEVELS: dict[int, EventLevel] = {
    1: "critical",
    2: "error",
    3: "warning",
    4: "information",
}
_LEVEL_CODES = {value: key for key, value in _LEVELS.items()}
_ALLOWED_CHANNELS = {"Application", "System"}
_ERROR_INSUFFICIENT_BUFFER = 122
_ERROR_ACCESS_DENIED = 5
_ERROR_NO_MORE_ITEMS = 259
_ERROR_TIMEOUT = 1460
_EVT_QUERY_CHANNEL_PATH = 0x1
_EVT_QUERY_REVERSE_DIRECTION = 0x200
_EVT_RENDER_EVENT_XML = 1
# DOMAIN\user only. Filesystem path segments such as "Files\App" inside
# "C:\Program Files\App\app.exe" must not be treated as accounts, so a match
# cannot sit on either side of a path separator. The trailing lookahead also
# blocks a backtracked partial match ("Files\A" out of "Files\App\...").
_ACCOUNT = re.compile(
    r"(?<![\\/:])(?<![\w.-])(?:[A-Za-z0-9_.-]{1,64})\\([A-Za-z0-9_.@$-]{1,64})(?![\\/:.\w])"
)
_ACCOUNT_FILE_SUFFIX = re.compile(
    r"(?i)\.(exe|dll|sys|com|bat|cmd|ps1|vbs|js|wsf|msi|txt|log|xml|json|ini|dat|bin|drv)$"
)
# Event records are local XML; a hostile or corrupt payload must not be allowed
# to exhaust memory before the parser rejects it.
_MAX_EVENT_XML_CHARS = 256 * 1024


def _redact_account(match: re.Match[str]) -> str:
    if _ACCOUNT_FILE_SUFFIX.search(match.group(1)):
        return match.group(0)
    return "[ACCOUNT_REDACTED]"


def redact_event_text(value: str, *, limit: int = 1000) -> str:
    normalized = " ".join(value.replace("\x00", " ").split())
    normalized = redact_text(normalized)
    normalized = _ACCOUNT.sub(_redact_account, normalized)
    if len(normalized) > limit:
        return f"{normalized[: limit - 1]}…"
    return normalized


def _first(values: dict[str, str], *names: str) -> str | None:
    folded = {key.casefold(): value for key, value in values.items()}
    for name in names:
        if value := folded.get(name.casefold()):
            return value
    return None


def _safe_filename(value: str | None) -> str | None:
    if not value:
        return None
    basename = ntpath.basename(value.strip().strip('"'))
    return redact_event_text(basename, limit=260) or None


def parse_event_xml(xml: str, channel: str) -> WindowsEvent | None:
    if channel not in _ALLOWED_CHANNELS:
        return None
    if not isinstance(xml, str) or not xml or len(xml) > _MAX_EVENT_XML_CHARS:
        return None
    try:
        # defusedxml rejects DTD/entity expansion; the catch below also covers
        # deep nesting that blows the interpreter stack while walking nodes.
        root = _safe_fromstring(xml)
        namespace = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
        system = root.find("e:System", namespace)
        if system is None:
            return None
        provider_node = system.find("e:Provider", namespace)
        event_id_node = system.find("e:EventID", namespace)
        level_node = system.find("e:Level", namespace)
        time_node = system.find("e:TimeCreated", namespace)
        if event_id_node is None or level_node is None or time_node is None:
            return None
        level = _LEVELS.get(int(level_node.text or "0"))
        timestamp = time_node.attrib.get("SystemTime")
        if level is None or not timestamp:
            return None

        values: dict[str, str] = {}
        unnamed: list[str] = []
        event_data = root.find("e:EventData", namespace)
        if event_data is not None:
            for index, node in enumerate(event_data.findall("e:Data", namespace)):
                text = node.text or ""
                name = node.attrib.get("Name")
                values[name or f"Data{index}"] = text
                if text:
                    unnamed.append(text)
        if not unnamed:
            for node in root.findall(".//e:UserData//*", namespace):
                if node.text and node.text.strip():
                    unnamed.append(node.text)

        application = _safe_filename(
            _first(
                values,
                "AppName",
                "FaultingApplicationName",
                "ApplicationName",
                "P1",
                "Data0",
            )
        )
        module = _safe_filename(
            _first(
                values,
                "ModuleName",
                "FaultingModuleName",
                "FaultingModulePath",
                "P4",
                "Data3",
            )
        )
        exception_code = _first(values, "ExceptionCode", "Exception Code", "P7", "Data6")
        summary_parts = [redact_event_text(item, limit=240) for item in unnamed[:8]]
        summary = " · ".join(item for item in summary_parts if item)
        if not summary:
            summary = "事件未提供可用的结构化详情。"
        return WindowsEvent(
            channel=cast("LogChannel", channel),
            provider=(
                provider_node.attrib.get("Name", "Unknown")
                if provider_node is not None
                else "Unknown"
            ),
            event_id=int(event_id_node.text or "0"),
            level=level,
            timestamp=timestamp,
            summary=redact_event_text(summary),
            application=application,
            faulting_module=module,
            exception_code=(
                redact_event_text(exception_code, limit=80) if exception_code else None
            ),
        )
    except (
        ElementTree.ParseError,
        DefusedXmlException,
        TypeError,
        ValueError,
        RecursionError,
        MemoryError,
    ):
        return None


def _xpath(query: EventLogQuery) -> str:
    milliseconds = query.lookback_hours * 60 * 60 * 1000
    clauses = [f"TimeCreated[timediff(@SystemTime) <= {milliseconds}]"]
    level_codes = [_LEVEL_CODES[level] for level in query.levels]
    clauses.append("(" + " or ".join(f"Level={code}" for code in level_codes) + ")")
    if query.event_ids:
        clauses.append("(" + " or ".join(f"EventID={value}" for value in query.event_ids) + ")")
    return "*[System[" + " and ".join(clauses) + "]]"


class WindowsEventLogProbe:
    def __init__(self, api: Any | None = None) -> None:
        if api is not None:
            self._api = api
        elif sys.platform == "win32":
            self._api = ctypes.WinDLL("wevtapi", use_last_error=True)
            self._configure_api()
        else:
            self._api = None

    def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]:
        if self._api is None:
            raise ToolUnavailableError("Windows Event Log API is unavailable on this platform.")
        if query.channel not in _ALLOWED_CHANNELS:
            raise ValueError("Event log channel is not allowlisted.")
        if not 1 <= query.lookback_hours <= 168 or not 1 <= query.max_events <= 200:
            raise ValueError("Event log query exceeds the bounded policy.")
        if not query.levels or any(level not in _LEVEL_CODES for level in query.levels):
            raise ValueError("Event log level is not allowlisted.")
        if len(query.event_ids) > 32 or any(
            event_id < 0 or event_id > 65535 for event_id in query.event_ids
        ):
            raise ValueError("Event ID filter exceeds the bounded policy.")

        result_handle = self._api.EvtQuery(
            None,
            query.channel,
            _xpath(query),
            _EVT_QUERY_CHANNEL_PATH | _EVT_QUERY_REVERSE_DIRECTION,
        )
        if not result_handle:
            self._raise_last_error("Windows rejected the event log query.")
        events: list[WindowsEvent] = []
        handles = (wintypes.HANDLE * 16)()
        returned = wintypes.DWORD()
        deadline = time.monotonic() + 10.0
        try:
            while len(events) < query.max_events:
                if cancel_event.is_set():
                    raise ToolCancelledError("Event log query was cancelled.")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Windows Event Log query exceeded its adapter deadline.")
                success = self._api.EvtNext(
                    result_handle, len(handles), handles, 250, 0, ctypes.byref(returned)
                )
                if not success:
                    error = ctypes.get_last_error()
                    if error == _ERROR_NO_MORE_ITEMS:
                        break
                    if error == _ERROR_TIMEOUT:
                        continue
                    self._raise_error(error, "Windows could not enumerate event log records.")
                for index in range(returned.value):
                    raw_handle = handles[index]
                    if raw_handle is None:
                        continue
                    event_handle = wintypes.HANDLE(raw_handle)
                    try:
                        if len(events) < query.max_events:
                            parsed = parse_event_xml(self._render_xml(event_handle), query.channel)
                            if parsed is not None:
                                events.append(parsed)
                    finally:
                        self._api.EvtClose(event_handle)
        finally:
            self._api.EvtClose(result_handle)
        events.sort(key=lambda item: _event_time(item.timestamp), reverse=True)
        return tuple(events)

    def _render_xml(self, event_handle: wintypes.HANDLE) -> str:
        used = wintypes.DWORD()
        properties = wintypes.DWORD()
        self._api.EvtRender(
            None,
            event_handle,
            _EVT_RENDER_EVENT_XML,
            0,
            None,
            ctypes.byref(used),
            ctypes.byref(properties),
        )
        error = ctypes.get_last_error()
        if error != _ERROR_INSUFFICIENT_BUFFER:
            self._raise_error(error, "Windows could not render an event record.")
        buffer = ctypes.create_unicode_buffer(max(1, used.value // ctypes.sizeof(ctypes.c_wchar)))
        if not self._api.EvtRender(
            None,
            event_handle,
            _EVT_RENDER_EVENT_XML,
            used.value,
            buffer,
            ctypes.byref(used),
            ctypes.byref(properties),
        ):
            self._raise_last_error("Windows could not render an event record.")
        return buffer.value

    def _configure_api(self) -> None:
        self._api.EvtQuery.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
        ]
        self._api.EvtQuery.restype = wintypes.HANDLE
        self._api.EvtNext.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._api.EvtNext.restype = wintypes.BOOL
        self._api.EvtRender.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._api.EvtRender.restype = wintypes.BOOL
        self._api.EvtClose.argtypes = [wintypes.HANDLE]
        self._api.EvtClose.restype = wintypes.BOOL

    @staticmethod
    def _raise_error(error: int, message: str) -> None:
        if error == _ERROR_ACCESS_DENIED:
            raise ToolPermissionError("当前账户无权读取该事件日志通道。")
        raise ToolUnavailableError(f"{message} Windows error {error}.")

    def _raise_last_error(self, message: str) -> None:
        self._raise_error(ctypes.get_last_error(), message)
