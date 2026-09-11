import os
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from sysmind.actions import ActionCoordinator
from sysmind.agent.contracts import AgentProvider
from sysmind.agent.planning import FakeDiagnosisPlanner, ProviderDiagnosisPlanner
from sysmind.agent.providers import FakeProvider, OpenAICompatibleProviderFactory
from sysmind.application.ports.secrets import SecretService
from sysmind.application.services import (
    HistoryService,
    LogAnalysisCoordinator,
    ProviderSettingsService,
    QuickScanCoordinator,
)
from sysmind.diagnosis import DiagnosisCoordinator
from sysmind.infrastructure.database import create_session_factory
from sysmind.infrastructure.database.repositories import (
    SqlAlchemyActionRepository,
    SqlAlchemyAgentTaskRepository,
    SqlAlchemyDiagnosisRepository,
    SqlAlchemyHistoryRepository,
    SqlAlchemyLogAnalysisRepository,
    SqlAlchemyProviderSettingsRepository,
    SqlAlchemyScanRepository,
)
from sysmind.infrastructure.secrets import FakeSecretService, WindowsCredentialSecretService
from sysmind.prompts import (
    LocalReportExplainer,
    ProviderReportExplainer,
    ReportExplainer,
)
from sysmind.security import ConsentService
from sysmind.tasks import AgentTaskManager
from sysmind.tools.log import LogTools
from sysmind.tools.process import ProcessTools
from sysmind.tools.runtime_tools import build_runtime_registry
from sysmind.tools.system import SystemTools
from sysmind.windows import (
    WindowsEventLogProbe,
    WindowsNetworkProbe,
    WindowsProcessProbe,
    WindowsServiceProbe,
    WindowsStartupProbe,
    WindowsSystemProbe,
)
from sysmind.windows.process_actions import WindowsProcessActionAdapter
from sysmind.windows.startup_actions import WindowsStartupActionAdapter


def _resolve_sessions(
    database_url: str, sessions: sessionmaker[Session] | None
) -> sessionmaker[Session]:
    """Return the caller-supplied session factory, or build a dedicated one.

    The composition root should create a single ``sessionmaker`` and inject it into
    every factory so all repositories share one engine against the same SQLite file.
    The ``database_url`` fallback exists so tests and tools can construct an
    individual service without wiring the whole graph.
    """
    return sessions if sessions is not None else create_session_factory(database_url)


def create_quick_scan_coordinator(
    database_url: str, sessions: sessionmaker[Session] | None = None
) -> QuickScanCoordinator:
    repository = SqlAlchemyScanRepository(_resolve_sessions(database_url, sessions))
    return QuickScanCoordinator(
        repository,
        SystemTools(WindowsSystemProbe()),
        ProcessTools(WindowsProcessProbe()),
    )


def create_log_analysis_coordinator(
    database_url: str, sessions: sessionmaker[Session] | None = None
) -> LogAnalysisCoordinator:
    repository = SqlAlchemyLogAnalysisRepository(_resolve_sessions(database_url, sessions))
    return LogAnalysisCoordinator(repository, LogTools(WindowsEventLogProbe()))


def create_provider_settings_service(
    database_url: str,
    secrets: SecretService | None = None,
    sessions: sessionmaker[Session] | None = None,
) -> ProviderSettingsService:
    if secrets is None:
        secrets = WindowsCredentialSecretService() if os.name == "nt" else FakeSecretService()
    return ProviderSettingsService(
        SqlAlchemyProviderSettingsRepository(_resolve_sessions(database_url, sessions)),
        secrets,
        OpenAICompatibleProviderFactory(),
    )


def create_history_service(
    database_url: str, sessions: sessionmaker[Session] | None = None
) -> HistoryService:
    return HistoryService(
        SqlAlchemyHistoryRepository(_resolve_sessions(database_url, sessions))
    )


def create_agent_task_manager(
    database_url: str,
    provider_settings: ProviderSettingsService | None = None,
    sessions: sessionmaker[Session] | None = None,
) -> AgentTaskManager:
    repository = SqlAlchemyAgentTaskRepository(_resolve_sessions(database_url, sessions))
    registry = build_runtime_registry(
        WindowsSystemProbe(),
        WindowsProcessProbe(),
        WindowsEventLogProbe(),
        WindowsNetworkProbe(),
        WindowsStartupProbe(),
        WindowsServiceProbe(),
    )

    def provider_factory() -> AgentProvider:
        if provider_settings is not None:
            provider = provider_settings.configured_provider()
            if provider is not None:
                return provider
        return FakeProvider()

    return AgentTaskManager(repository, registry, provider_factory)


def create_diagnosis_coordinator(
    database_url: str,
    provider_settings: ProviderSettingsService | None = None,
    sessions: sessionmaker[Session] | None = None,
) -> DiagnosisCoordinator:
    repository = SqlAlchemyDiagnosisRepository(_resolve_sessions(database_url, sessions))
    registry = build_runtime_registry(
        WindowsSystemProbe(),
        WindowsProcessProbe(),
        WindowsEventLogProbe(),
        WindowsNetworkProbe(),
        WindowsStartupProbe(),
        WindowsServiceProbe(),
    )

    def explainer_factory() -> ReportExplainer:
        if provider_settings is not None:
            provider = provider_settings.configured_provider()
            if provider is not None:
                return ProviderReportExplainer(provider)
        return LocalReportExplainer()

    def planner_factory() -> FakeDiagnosisPlanner | ProviderDiagnosisPlanner:
        if provider_settings is not None:
            provider = provider_settings.configured_provider()
            if provider is not None:
                return ProviderDiagnosisPlanner(registry, provider)
        return FakeDiagnosisPlanner(registry)

    return DiagnosisCoordinator(repository, registry, explainer_factory, planner_factory)


def create_action_coordinator(
    database_url: str,
    data_dir: Path,
    session_binding: str,
    sessions: sessionmaker[Session] | None = None,
) -> ActionCoordinator:
    resolved_sessions = _resolve_sessions(database_url, sessions)
    return ActionCoordinator(
        SqlAlchemyActionRepository(resolved_sessions),
        SqlAlchemyDiagnosisRepository(resolved_sessions),
        WindowsStartupActionAdapter(data_dir / "action-recovery"),
        ConsentService(session_binding),
        WindowsProcessActionAdapter(),
    )
