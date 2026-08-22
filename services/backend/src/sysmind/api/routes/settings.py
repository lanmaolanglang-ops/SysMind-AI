from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request

from sysmind.api.dto.settings import (
    ProviderSettingsResponse,
    ProviderTestResponse,
    UpdateProviderSettingsRequest,
)
from sysmind.application.services.provider_settings import (
    ProviderSettingsService,
    PublicProviderSettings,
)

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
    return _response(_service(request).get())


@router.put("/settings", response_model=ProviderSettingsResponse)
async def update_settings(
    payload: UpdateProviderSettingsRequest, request: Request
) -> ProviderSettingsResponse:
    try:
        value = _service(request).save(
            payload.provider, payload.model, str(payload.endpoint), payload.api_key
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _response(value, restart_required=True)


@router.delete("/settings/credential", response_model=ProviderSettingsResponse)
async def clear_credential(request: Request) -> ProviderSettingsResponse:
    return _response(_service(request).clear_credential(), restart_required=True)


@router.post("/providers/test", response_model=ProviderTestResponse)
async def test_provider(request: Request) -> ProviderTestResponse:
    try:
        succeeded, error_code, duration_ms = await _service(request).test_connection()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return ProviderTestResponse(
        succeeded=succeeded, error_code=error_code, duration_ms=duration_ms
    )
