from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from sysmind.api.dto.settings import (
    ProviderSettingsResponse,
    ProviderTestResponse,
    UpdateProviderSettingsRequest,
)
from sysmind.application.services.provider_settings import (
    ProviderSettingsService,
    PublicProviderSettings,
)
from sysmind.tools.contracts import ToolUnavailableError

router = APIRouter(prefix="/api/v1", tags=["settings"])


def _service(request: Request) -> ProviderSettingsService:
    return cast(ProviderSettingsService, request.app.state.provider_settings_service)


def _response(
    value: PublicProviderSettings, *, restart_required: bool = False
) -> ProviderSettingsResponse:
    return ProviderSettingsResponse(
        provider=value.provider,
        model=value.model,
        endpoint=value.endpoint,
        configured=value.configured,
        updated_at=value.updated_at,
        restart_required=restart_required,
    )


@router.get("/settings", response_model=ProviderSettingsResponse)
async def get_settings(request: Request) -> ProviderSettingsResponse:
    # Service calls hit SQLite and the blocking Windows credential store; keep
    # them off the event loop like every other route.
    value = await run_in_threadpool(_service(request).get)
    return _response(value)


@router.put("/settings", response_model=ProviderSettingsResponse)
async def update_settings(
    payload: UpdateProviderSettingsRequest, request: Request
) -> ProviderSettingsResponse:
    try:
        value = await run_in_threadpool(
            _service(request).save,
            payload.provider,
            payload.model,
            str(payload.endpoint),
            payload.api_key,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ToolUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail="Windows 凭据存储暂不可用，设置未保存。",
        ) from error
    return _response(value, restart_required=True)


@router.delete("/settings/credential", response_model=ProviderSettingsResponse)
async def clear_credential(request: Request) -> ProviderSettingsResponse:
    try:
        value = await run_in_threadpool(_service(request).clear_credential)
    except ToolUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail="Windows 凭据存储暂不可用，访问密钥未清除。",
        ) from error
    return _response(value, restart_required=True)


@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_provider(request: Request) -> ProviderTestResponse:
    try:
        succeeded, error_code, duration_ms = await _service(request).test_connection()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ProviderTestResponse(
        succeeded=succeeded, error_code=error_code, duration_ms=duration_ms
    )
