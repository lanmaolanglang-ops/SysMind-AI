from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sysmind.actions import ActionCoordinator
from sysmind.api.middleware import LocalApiSecurityMiddleware
from sysmind.api.routes.actions import router as actions_router
from sysmind.api.routes.agent_tasks import router as agent_tasks_router
from sysmind.api.routes.diagnoses import router as diagnoses_router
from sysmind.api.routes.health import router as health_router
from sysmind.api.routes.log_analyses import router as log_analyses_router
from sysmind.api.routes.scans import router as scans_router
from sysmind.application.services import LogAnalysisCoordinator, QuickScanCoordinator
from sysmind.core.config import Settings, get_settings
from sysmind.core.constants import API_VERSION, BACKEND_VERSION
from sysmind.diagnosis import DiagnosisCoordinator
from sysmind.infrastructure.bootstrap import (
    create_action_coordinator,
    create_agent_task_manager,
    create_diagnosis_coordinator,
    create_log_analysis_coordinator,
    create_quick_scan_coordinator,
)
from sysmind.infrastructure.database import run_migrations
from sysmind.observability.logging import configure_logging
from sysmind.runtime.shutdown import ShutdownController
from sysmind.tasks import AgentTaskManager


def create_app(
    settings: Settings | None = None,
    shutdown_controller: ShutdownController | None = None,
    quick_scan_coordinator: QuickScanCoordinator | None = None,
    log_analysis_coordinator: LogAnalysisCoordinator | None = None,
    agent_task_manager: AgentTaskManager | None = None,
    diagnosis_coordinator: DiagnosisCoordinator | None = None,
    action_coordinator: ActionCoordinator | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    controller = shutdown_controller or ShutdownController()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings.data_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(resolved_settings.database_url)
        coordinator = quick_scan_coordinator or create_quick_scan_coordinator(
            resolved_settings.database_url
        )
        app.state.quick_scan_coordinator = coordinator
        coordinator.recover_interrupted()
        log_coordinator = log_analysis_coordinator or create_log_analysis_coordinator(
            resolved_settings.database_url
        )
        app.state.log_analysis_coordinator = log_coordinator
        log_coordinator.recover_interrupted()
        task_manager = agent_task_manager or create_agent_task_manager(
            resolved_settings.database_url
        )
        app.state.agent_task_manager = task_manager
        task_manager.recover_interrupted()
        diagnoses = diagnosis_coordinator or create_diagnosis_coordinator(
            resolved_settings.database_url
        )
        app.state.diagnosis_coordinator = diagnoses
        diagnoses.recover_interrupted()
        actions = action_coordinator or create_action_coordinator(
            resolved_settings.database_url,
            resolved_settings.data_dir,
            resolved_settings.session_token.get_secret_value(),
        )
        app.state.action_coordinator = actions
        actions.recover_interrupted()
        app.state.ready = True
        yield
        app.state.ready = False
        await coordinator.shutdown()
        await log_coordinator.shutdown()
        await task_manager.shutdown()
        await diagnoses.shutdown()
        actions.shutdown()

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
        allow_headers=[
            "Content-Type",
            "X-SysMind-Session",
            "X-Correlation-ID",
            "Last-Event-ID",
        ],
        expose_headers=["X-Correlation-ID"],
    )
    app.include_router(health_router)
    app.include_router(scans_router)
    app.include_router(log_analyses_router)
    app.include_router(agent_tasks_router)
    app.include_router(diagnoses_router)
    app.include_router(actions_router)
    return app
