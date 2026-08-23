import os
from pathlib import Path

from sysmind.actions import ActionCoordinator
from sysmind.agent.contracts import AgentProvider
from sysmind.agent.planning import FakeDiagnosisPlanner, ProviderDiagnosisPlanner
from sysmind.agent.providers import FakeProvider
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


def create_quick_scan_coordinator(database_url: str) -> QuickScanCoordinator:
    repository = SqlAlchemyScanRepository(create_session_factory(database_url))
    return QuickScanCoordinator(
        repository,
        SystemTools(WindowsSystemProbe()),
        ProcessTools(WindowsProcessProbe()),
    )


def create_log_analysis_coordinator(database_url: str) -> LogAnalysisCoordinator:
    repository = SqlAlchemyLogAnalysisRepository(create_session_factory(database_url))
    return LogAnalysisCoordinator(repository, LogTools(WindowsEventLogProbe()))


def create_provider_settings_service(
    database_url: str, secrets: SecretService | None = None
) -> ProviderSettingsService:
    if secrets is None:
        secrets = WindowsCredentialSecretService() if os.name == "nt" else FakeSecretService()
    return ProviderSettingsService(
        SqlAlchemyProviderSettingsRepository(create_session_factory(database_url)), secrets
    )


def create_history_service(database_url: str) -> HistoryService:
    return HistoryService(SqlAlchemyHistoryRepository(create_session_factory(database_url)))


def create_agent_task_manager(
    database_url: str, provider_settings: ProviderSettingsService | None = None
) -> AgentTaskManager:
    repository = SqlAlchemyAgentTaskRepository(create_session_factory(database_url))
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
    database_url: str, provider_settings: ProviderSettingsService | None = None
) -> DiagnosisCoordinator:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(database_url))
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
    database_url: str, data_dir: Path, session_binding: str
) -> ActionCoordinator:
    sessions = create_session_factory(database_url)
    return ActionCoordinator(
        SqlAlchemyActionRepository(sessions),
        SqlAlchemyDiagnosisRepository(sessions),
        WindowsStartupActionAdapter(data_dir / "action-recovery"),
        ConsentService(session_binding),
        WindowsProcessActionAdapter(),
    )
