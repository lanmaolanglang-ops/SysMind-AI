from fastapi.testclient import TestClient

from sysmind.core.constants import API_VERSION, BACKEND_VERSION
from sysmind.runtime.shutdown import ShutdownController


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
    assert response.headers["X-Correlation-ID"]


def test_health_rejects_missing_session(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"


def test_health_rejects_unknown_origin(client: TestClient) -> None:
    response = client.get(
        "/health",
        headers={
            "X-SysMind-Session": "test-session-token-that-is-long-enough",
            "Origin": "https://example.com",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


def test_health_allows_vite_loopback_origin(client: TestClient) -> None:
    response = client.get(
        "/health",
        headers={
            "X-SysMind-Session": "test-session-token-that-is-long-enough",
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
