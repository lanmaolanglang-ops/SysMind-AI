from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from sysmind.api.middleware import _tokens_match
from sysmind.core.constants import API_VERSION, BACKEND_VERSION
from sysmind.runtime.shutdown import ShutdownController
from tests.conftest import TEST_TOKEN


def test_health_returns_versioned_readiness(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/health", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "backend_version": BACKEND_VERSION,
        "api_version": API_VERSION,
        "ready": True,
    }
    # No correlation id was supplied, so the server must generate a well-formed UUID.
    uuid.UUID(response.headers["X-Correlation-ID"])


def test_health_rejects_missing_session(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"


def test_health_rejects_unknown_origin(client: TestClient) -> None:
    response = client.get(
        "/health",
        headers={
            "X-SysMind-Session": TEST_TOKEN,
            "Origin": "https://example.com",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


def test_health_allows_vite_loopback_origin(client: TestClient) -> None:
    response = client.get(
        "/health",
        headers={
            "X-SysMind-Session": TEST_TOKEN,
            "Origin": "http://127.0.0.1:1420",
        },
    )

    assert response.status_code == 200


def test_shutdown_requests_graceful_stop(
    client: TestClient,
    auth_headers: dict[str, str],
    shutdown_controller: ShutdownController,
) -> None:
    response = client.post("/internal/shutdown", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"status": "shutting_down"}
    assert shutdown_controller.requested is True


def test_state_changing_request_requires_origin(
    client: TestClient, shutdown_controller: ShutdownController
) -> None:
    response = client.post(
        "/internal/shutdown",
        headers={"X-SysMind-Session": TEST_TOKEN, "Content-Length": "0"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_required"
    assert shutdown_controller.requested is False


def test_non_ascii_session_token_comparison_is_safe() -> None:
    assert _tokens_match("令牌", TEST_TOKEN) is False


def test_request_body_limit_rejects_declared_oversize_payload(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/internal/shutdown",
        headers={**auth_headers, "Content-Length": str(2 * 1024 * 1024 + 1)},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_local_api_rejects_chunked_request_bodies(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/internal/shutdown",
        headers={**auth_headers, "Transfer-Encoding": "chunked"},
    )

    assert response.status_code == 411
    assert response.json()["error"]["code"] == "content_length_required"


def test_health_replaces_a_client_supplied_correlation_id_that_is_not_safe(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/health",
        headers={**auth_headers, "X-Correlation-ID": "not a valid; id"},
    )

    assert response.status_code == 200
    echoed = response.headers["X-Correlation-ID"]
    assert echoed != "not a valid; id"
    uuid.UUID(echoed)


def test_health_echoes_a_well_formed_correlation_id(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get(
        "/health", headers={**auth_headers, "X-Correlation-ID": "correlation-abc-123"}
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "correlation-abc-123"
