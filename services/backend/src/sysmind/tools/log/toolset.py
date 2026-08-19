from __future__ import annotations

from collections.abc import Sequence
from threading import Event

from sysmind.application.ports.event_logs import EventLogProbe
from sysmind.domain.event_logs import CrashGroup, EventGroup, EventLogQuery, WindowsEvent
from sysmind.tools.contracts import ToolSpec

LOG_TOOL_SPECS = (
    ToolSpec("log.windows_event.query", "1.0", 12.0),
    ToolSpec("log.crash.analyze", "1.0", 3.0),
)


def _crash_key(event: WindowsEvent) -> tuple[str, str | None, str | None]:
    return (
        event.application or "未知应用",
        event.faulting_module,
        event.exception_code,
    )


def analyze_crashes(events: Sequence[WindowsEvent]) -> tuple[CrashGroup, ...]:
    grouped: dict[tuple[str, str | None, str | None], list[WindowsEvent]] = {}
    for event in events:
        provider = event.provider.casefold()
        is_crash_provider = "application error" in provider or "windows error reporting" in provider
        if event.channel == "Application" and (is_crash_provider or event.event_id in {1000, 1001}):
            grouped.setdefault(_crash_key(event), []).append(event)

    results = [
        CrashGroup(
            application=key[0],
            faulting_module=key[1],
            exception_code=key[2],
            count=len(items),
            latest_at=max(item.timestamp for item in items),
            evidence_event_ids=tuple(sorted({item.event_id for item in items})),
            providers=tuple(sorted({item.provider for item in items})),
        )
        for key, items in grouped.items()
    ]
    results.sort(key=lambda item: (item.count, item.latest_at), reverse=True)
    return tuple(results)


def aggregate_events(events: Sequence[WindowsEvent]) -> tuple[EventGroup, ...]:
    grouped: dict[tuple[str, str, int, str], list[WindowsEvent]] = {}
    for event in events:
        key = (event.channel, event.provider, event.event_id, event.level)
        grouped.setdefault(key, []).append(event)
    results = [
        EventGroup(
            channel=items[0].channel,
            provider=items[0].provider,
            event_id=items[0].event_id,
            level=items[0].level,
            count=len(items),
            latest_at=max(item.timestamp for item in items),
            sample_summary=max(items, key=lambda item: item.timestamp).summary,
        )
        for items in grouped.values()
    ]
    results.sort(key=lambda item: (item.count, item.latest_at), reverse=True)
    return tuple(results)


class LogTools:
    def __init__(self, probe: EventLogProbe) -> None:
        self._probe = probe

    def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]:
        return self._probe.query(query, cancel_event)

    @staticmethod
    def analyze(events: Sequence[WindowsEvent]) -> tuple[CrashGroup, ...]:
        return analyze_crashes(events)

    @staticmethod
    def aggregate(events: Sequence[WindowsEvent]) -> tuple[EventGroup, ...]:
        return aggregate_events(events)
