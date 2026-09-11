from fastapi import APIRouter, Request

from sysmind.api.dto import HealthResponse, ShutdownResponse
from sysmind.core.constants import API_VERSION, BACKEND_VERSION
from sysmind.runtime.shutdown import ShutdownController

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
    controller.request_shutdown()
    return ShutdownResponse()
