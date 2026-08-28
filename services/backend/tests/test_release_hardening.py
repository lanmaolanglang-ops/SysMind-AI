from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from sysmind.actions import ActionError
from sysmind.api.dto.agent_tasks import StartAgentTaskRequest
from sysmind.observability.logging import log_event
from sysmind.reports.redaction import redact_text
from sysmind.security.redaction import is_sensitive_key
from tests.test_phase5_actions import FakeStartupActions, coordinator

BACKSLASH = chr(92)


def test_consume_confirmation_is_single_use_and_expiry_bound(tmp_path) -> None:
    service, _adapter = coordinator(tmp_path)
    now = datetime.now(UTC)
    candidate = service.candidates("diagnosis-ready")[0]
    action = service.create_disable(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    repository = service._repository  # noqa: SLF001 - test seam for the CAS boundary
    repository.add_confirmation(
        action.id,
        ticket_digest="d" * 64,
        expires_at=(now + timedelta(seconds=120)).isoformat(),
        created_at=now.isoformat(),
    )
    assert repository.consume_confirmation(
        action.id, ticket_digest="d" * 64, consumed_at=now.isoformat()
    )
    assert not repository.consume_confirmation(
        action.id, ticket_digest="d" * 64, consumed_at=now.isoformat()
    )

    repository.add_confirmation(
        action.id,
        ticket_digest="e" * 64,
        expires_at=(now - timedelta(seconds=1)).isoformat(),
        created_at=now.isoformat(),
    )
    assert not repository.consume_confirmation(
        action.id, ticket_digest="e" * 64, consumed_at=now.isoformat()
    )


def test_execute_maps_unexpected_adapter_error_to_terminal_failure(tmp_path) -> None:
    class ExplodingStartupActions(FakeStartupActions):
        def disable(self, item_id: str, observed_revision: str) -> object:
            raise RuntimeError("simulated adapter crash")

    service, _adapter = coordinator(tmp_path)
    candidate = service.candidates("diagnosis-ready")[0]
    action = service.create_disable(
        "diagnosis-ready", candidate.item_id, candidate.observed_revision
    )
    confirmed, ticket, _expires = service.confirm(action.id)
    assert confirmed.status == "confirmed"
    # Swap in an adapter that raises outside every mapped error family.
    service._adapter = ExplodingStartupActions()  # noqa: SLF001 - test seam
    finished = service.execute(action.id, ticket)
    assert finished.status == "failed"
    assert finished.error_code == "action_failed"
    with pytest.raises(ActionError, match="not awaiting execution"):
        service.execute(action.id, ticket)


def test_redact_text_covers_user_paths_ips_and_mac_addresses() -> None:
    redacted = redact_text(
        "path C:"
        + BACKSLASH
        + "Users"
        + BACKSLASH
        + "alice"
        + BACKSLASH
        + "AppData"
        + " unix C:/Users/bob(x) unc "
        + BACKSLASH * 2
        + "SERVER"
        + BACKSLASH
        + "Users"
        + BACKSLASH
        + "carol"
        + BACKSLASH
        + "doc, ip 192.168.0.9 v6 fe80::1f, mac 00-1A-2B-3C-4D-5E, mail a@b.com"
    )
    assert "alice" not in redacted
    assert "bob" not in redacted
    assert "carol" not in redacted
    assert "192.168.0.9" not in redacted
    assert "fe80::1f" not in redacted
    assert "00-1A-2B-3C-4D-5E" not in redacted
    assert "a@b.com" not in redacted


def test_redact_text_keeps_timestamps_and_non_user_paths() -> None:
    text = "12:34:56 and 2026-08-28T12:34:56 plus " + BACKSLASH + "server" + BACKSLASH + "c$"
    assert redact_text(text) == text


def test_redact_text_covers_paths_without_trailing_separator() -> None:
    end_of_line = "profile C:" + BACKSLASH + "Users" + BACKSLASH + "jane"
    assert "jane" not in redact_text(end_of_line)
    space_terminated = BACKSLASH * 2 + "srv" + BACKSLASH + "Users" + BACKSLASH + "carol doc"
    redacted = redact_text(space_terminated)
    assert "carol" not in redacted
    assert " doc" in redacted


def test_redact_event_text_uses_shared_rules() -> None:
    from sysmind.windows.event_logs import redact_event_text

    redacted = redact_event_text(
        "fail on \\\\".replace("\\\\", BACKSLASH * 2)
        + "fs"
        + BACKSLASH
        + "Users"
        + BACKSLASH
        + "ken"
        + BACKSLASH
        + "notes.txt from 10.1.2.3 fe80::1 00-1A-2B-3C-4D-5E"
    )
    assert "ken" not in redacted
    assert "10.1.2.3" not in redacted
    assert "fe80::1" not in redacted
    assert "00-1A-2B-3C-4D-5E" not in redacted


def test_is_sensitive_key_covers_common_token_names() -> None:
    for key in ("access_token", "refresh-token", "client_secret", "private_key", "pwd", "auth"):
        assert is_sensitive_key(key), key
    assert not is_sensitive_key("author")
    assert not is_sensitive_key("gpu_name")


def test_log_event_clamps_hostile_correlation_ids(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("hardening-test")
    hostile = "x" * 500 + " drop table"
    with caplog.at_level(logging.INFO, logger="hardening-test"):
        log_event(
            logger,
            logging.INFO,
            "probe",
            component="test",
            event_type="probe",
            correlation_id=hostile,
        )
    record = caplog.records[0]
    assert len(record.correlation_id) <= 64
    assert "drop table" not in record.correlation_id


def test_agent_task_request_rejects_oversized_tool_names() -> None:
    with pytest.raises(ValidationError):
        StartAgentTaskRequest(user_goal="卡", allowed_tools=["t" * 400])
    with pytest.raises(ValidationError):
        StartAgentTaskRequest(user_goal="卡", allowed_tools=["   "])
