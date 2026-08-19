from __future__ import annotations

from collections.abc import Sequence
from threading import Event
from typing import Protocol

from sysmind.domain.event_logs import EventLogQuery, WindowsEvent


class EventLogProbe(Protocol):
    def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]: ...
