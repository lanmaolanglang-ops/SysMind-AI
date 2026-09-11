from __future__ import annotations

import sys
import time
from collections.abc import Sequence
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import sysmind.application.services.log_analysis as log_analysis_module
from sysmind.api.app import create_app
from sysmind.application.services import LogAnalysisCoordinator
from sysmind.core.config import Settings
from sysmind.domain.event_logs import EventLogQuery, WindowsEvent
from sysmind.infrastructure.database import create_database_engine, create_session_factory
from sysmind.infrastructure.database.repositories import SqlAlchemyLogAnalysisRepository
from sysmind.tools.contracts import ToolCancelledError, ToolPermissionError, ToolSpec
from sysmind.tools.log import LogTools
from sysmind.windows.event_logs import WindowsEventLogProbe, parse_event_xml

FIXTURES = Path(__file__).parent / "fixtures" / "events"


def _event(
    channel: str = "Application",
    *,
    event_id: int = 1000,
    timestamp: str = "2026-08-19T10:00:00+00:00",
) -> WindowsEvent:
    return WindowsEvent(
        channel=channel,  # type: ignore[arg-type]
        provider=(
            "Application Error"
            if event_id == 1000
            else "Windows Error Reporting"
            if event_id == 1001
            else "Fixture Provider"
        ),
        event_id=event_id,
        level="error",
        timestamp=timestamp,
        summary="demo.exe stopped working",
        application="demo.exe" if event_id in {1000, 1001} else None,
        faulting_module="KERNELBASE.dll" if event_id in {1000, 1001} else None,
        exception_code="0xc0000005" if event_id in {1000, 1001} else None,
    )


class FixtureEventLogProbe:
    def __init__(self, fail_system: bool = False) -> None:
        self.fail_system = fail_system
        self.queries: list[EventLogQuery] = []

    def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]:
        self.queries.append(query)
        if query.channel == "System" and self.fail_system:
            raise ToolPermissionError("当前账户无权读取该事件日志通道。")
        if query.channel == "Application":
            return (_event(), _event(event_id=1001, timestamp="2026-08-19T10:05:00+00:00"))
        return (_event("System", event_id=41),)


class SlowEventLogProbe(FixtureEventLogProbe):
    def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]:
        if cancel_event.wait(2):
            raise ToolCancelledError("cancelled")
        return ()


class TimeoutEventLogProbe(FixtureEventLogProbe):
    def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]:
        time.sleep(0.08)
        return ()


class PartiallySlowEventLogProbe(FixtureEventLogProbe):
    def __init__(self) -> None:
        super().__init__()
        self.system_started = Event()

    def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]:
        if query.channel == "Application":
            return super().query(query, cancel_event)
        self.system_started.set()
        if cancel_event.wait(2):
            raise ToolCancelledError("cancelled")
        return ()


def _client(settings: Settings, probe: FixtureEventLogProbe) -> TestClient:
    repository = SqlAlchemyLogAnalysisRepository(create_session_factory(settings.database_url))
    coordinator = LogAnalysisCoordinator(repository, LogTools(probe))
    return TestClient(create_app(settings, log_analysis_coordinator=coordinator))


def _wait_for_terminal(
    client: TestClient, analysis_id: str, headers: dict[str, str]
) -> dict[str, object]:
    for _ in range(150):
        payload = client.get(f"/api/v1/log-analyses/{analysis_id}", headers=headers).json()
        if payload["status"] in {"completed", "partial", "cancelled", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("log analysis did not reach a terminal state")


def test_event_xml_parser_is_language_independent_and_redacts_sensitive_values() -> None:
    english = parse_event_xml(
        (FIXTURES / "application_error_en.xml").read_text(encoding="utf-8"), "Application"
    )
    chinese = parse_event_xml((FIXTURES / "wer_zh.xml").read_text(encoding="utf-8"), "Application")

    assert english is not None
    assert english.application == "demo.exe"
    assert english.faulting_module == "KERNELBASE.dll"
    assert "Alice" not in english.summary
    assert "192.168.1.20" not in english.summary
    assert chinese is not None
    assert chinese.application == "demo.exe"
    assert "应用程序已停止工作" in chinese.summary


def test_corrupt_event_is_skipped_instead_of_breaking_the_query() -> None:
    assert (
        parse_event_xml((FIXTURES / "corrupt.xml").read_text(encoding="utf-8"), "Application")
        is None
    )


def test_unnamed_application_error_fields_use_the_stable_event_layout() -> None:
    xml = """<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
    <System><Provider Name="Application Error"/><EventID>1000</EventID><Level>2</Level>
    <TimeCreated SystemTime="2026-08-19T10:00:00Z"/></System><EventData>
    <Data>legacy.exe</Data><Data>1.0</Data><Data>0</Data><Data>module.dll</Data>
    <Data>1.0</Data><Data>0</Data><Data>0xc0000409</Data></EventData></Event>"""

    event = parse_event_xml(xml, "Application")

    assert event is not None
    assert event.application == "legacy.exe"
    assert event.faulting_module == "module.dll"
    assert event.exception_code == "0xc0000409"


def test_adapter_rechecks_policy_before_calling_windows() -> None:
    query = EventLogQuery(
        channel="Security",  # type: ignore[arg-type]
        lookback_hours=24,
        levels=("error",),
        event_ids=(),
        max_events=100,
    )

    with pytest.raises(ValueError, match="allowlisted"):
        WindowsEventLogProbe(api=object()).query(query, Event())


def test_analysis_preserves_results_when_one_channel_is_denied(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    probe = FixtureEventLogProbe(fail_system=True)
    with _client(settings, probe) as client:
        response = client.post(
            "/api/v1/log-analyses",
            headers=auth_headers,
            json={
                "channels": ["Application", "System"],
                "lookback_hours": 24,
                "levels": ["error", "information"],
                "max_events": 100,
            },
        )
        assert response.status_code == 202
        payload = _wait_for_terminal(client, response.json()["id"], auth_headers)

        assert payload["status"] == "partial"
        assert payload["schema_version"] == "1.0"
        assert payload["summary"]["event_count"] == 2
        assert payload["summary"]["event_groups"][0]["provider"] in {
            "Application Error",
            "Windows Error Reporting",
        }
        assert payload["summary"]["crash_groups"][0]["application"] == "demo.exe"
        assert payload["failures"][0]["code"] == "permission_required"
        assert all(query.lookback_hours == 24 for query in probe.queries)

    engine = create_database_engine(settings.database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT tool_name, arguments_hash, result_summary_json "
                "FROM event_log_step_events WHERE analysis_id = :analysis_id"
            ),
            {"analysis_id": payload["id"]},
        ).all()
    engine.dispose()
    # Assert the shape of the audit trail, not a brittle literal count.
    assert {row.tool_name for row in rows} == {
        "log.windows_event.query",
        "log.crash.analyze",
    }
    assert sum(1 for row in rows if row.tool_name == "log.crash.analyze") == 1
    assert all(len(row.arguments_hash) == 64 for row in rows)


@pytest.mark.parametrize(
    "body",
    [
        {"channels": ["Security"]},
        {"lookback_hours": 169},
        {"max_events": 201},
        {"levels": ["error", "error"]},
        {"event_ids": [70000]},
    ],
)
def test_api_rejects_unbounded_or_non_allowlisted_queries(
    settings: Settings, auth_headers: dict[str, str], body: dict[str, object]
) -> None:
    with _client(settings, FixtureEventLogProbe()) as client:
        response = client.post("/api/v1/log-analyses", headers=auth_headers, json=body)
    assert response.status_code == 422


def test_large_results_are_capped_by_the_requested_total(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    class LargeProbe(FixtureEventLogProbe):
        def query(self, query: EventLogQuery, cancel_event: Event) -> Sequence[WindowsEvent]:
            return tuple(
                _event(
                    query.channel,
                    event_id=2000 + index,
                    timestamp=f"2026-08-19T10:{index:02}:00+00:00",
                )
                for index in range(50)
            )

    with _client(settings, LargeProbe()) as client:
        response = client.post(
            "/api/v1/log-analyses", headers=auth_headers, json={"max_events": 20}
        )
        payload = _wait_for_terminal(client, response.json()["id"], auth_headers)
    assert payload["summary"]["event_count"] == 20
    assert len(payload["summary"]["events"]) == 20


def test_running_analysis_can_be_cancelled(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    with _client(settings, SlowEventLogProbe()) as client:
        response = client.post("/api/v1/log-analyses", headers=auth_headers, json={})
        analysis_id = response.json()["id"]
        cancelled = client.post(f"/api/v1/log-analyses/{analysis_id}/cancel", headers=auth_headers)
        assert cancelled.status_code == 200
        payload = _wait_for_terminal(client, analysis_id, auth_headers)
    assert payload["status"] == "cancelled"


def test_cancelled_analysis_keeps_consistent_partial_event_summary(
    settings: Settings, auth_headers: dict[str, str]
) -> None:
    probe = PartiallySlowEventLogProbe()
    with _client(settings, probe) as client:
        response = client.post(
            "/api/v1/log-analyses",
            headers=auth_headers,
            json={"channels": ["Application", "System"], "max_events": 1},
        )
        analysis_id = response.json()["id"]
        assert probe.system_started.wait(1)
        client.post(f"/api/v1/log-analyses/{analysis_id}/cancel", headers=auth_headers)
        payload = _wait_for_terminal(client, analysis_id, auth_headers)

    assert payload["status"] == "cancelled"
    assert payload["summary"]["event_count"] == 1
    assert len(payload["summary"]["events"]) == 1


def test_query_timeout_is_safe_and_audited(
    settings: Settings,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        log_analysis_module,
        "LOG_TOOL_SPECS",
        (
            ToolSpec("log.crash.analyze", "1.0", 1.0),
            ToolSpec("log.windows_event.query", "1.0", 0.01),
        ),
    )
    with _client(settings, TimeoutEventLogProbe()) as client:
        response = client.post(
            "/api/v1/log-analyses",
            headers=auth_headers,
            json={"channels": ["Application"]},
        )
        payload = _wait_for_terminal(client, response.json()["id"], auth_headers)
    assert payload["status"] == "failed"
    assert payload["failures"][0]["code"] == "tool_timeout"


@pytest.mark.windows_smoke
@pytest.mark.skipif(sys.platform != "win32", reason="Windows Event Log adapter smoke test")
def test_windows_event_log_adapter_smoke() -> None:
    query = EventLogQuery(
        channel="Application",
        lookback_hours=1,
        levels=("critical", "error", "warning", "information"),
        event_ids=(),
        max_events=5,
    )
    events = WindowsEventLogProbe().query(query, Event())

    assert len(events) <= 5
    assert all(event.channel == "Application" for event in events)
