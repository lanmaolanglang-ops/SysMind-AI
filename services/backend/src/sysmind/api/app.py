from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sysmind.api.middleware import LocalApiSecurityMiddleware
from sysmind.api.routes.health import router as health_router
from sysmind.core.config import Settings, get_settings
from sysmind.core.constants import API_VERSION, BACKEND_VERSION
from sysmind.infrastructure.database import run_migrations
from sysmind.observability.logging import configure_logging
from sysmind.runtime.shutdown import ShutdownController


def create_app(
    settings: Settings | None = None,
    shutdown_controller: ShutdownController | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    controller = shutdown_controller or ShutdownController()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings.data_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(resolved_settings.database_url)
        app.state.ready = True
        yield
        app.state.ready = False

    app = FastAPI(
        title="SysMind AI Local API",
        version=BACKEND_VERSION,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.shutdown_controller = controller
    app.state.api_version = API_VERSION
    app.add_middleware(LocalApiSecurityMiddleware, settings=resolved_settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.origin_allowlist),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-SysMind-Session", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
    )
    app.include_router(health_router)
    return app

