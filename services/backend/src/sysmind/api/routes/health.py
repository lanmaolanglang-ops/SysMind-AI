import logging

from fastapi import APIRouter, Request

from sysmind.api.dto import HealthResponse, ShutdownResponse
from sysmind.core.constants import API_VERSION, BACKEND_VERSION
from sysmind.observability.logging import log_event
from sysmind.runtime.shutdown import ShutdownController

_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["runtime"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        backend_version=BACKEND_VERSION,
        api_version=API_VERSION,
        ready=bool(getattr(request.app.state, "ready", False)),
    )


@router.post(
    "/internal/shutdown",
    response_model=ShutdownResponse,
    include_in_schema=False,
)
def shutdown(request: Request) -> ShutdownResponse:
    controller: ShutdownController = request.app.state.shutdown_controller
    # Shutdown is a system-changing control-plane action and must leave an audit trail.
    log_event(
        _LOGGER,
        logging.WARNING,
        "Local API shutdown requested.",
        component="runtime",
        event_type="shutdown_requested",
    )
    controller.request_shutdown()
    return ShutdownResponse()
