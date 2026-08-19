from pathlib import Path

from sysmind.actions import ActionCoordinator
from sysmind.agent.providers import FakeProvider
from sysmind.application.services import LogAnalysisCoordinator, QuickScanCoordinator
from sysmind.diagnosis import DiagnosisCoordinator
from sysmind.infrastructure.database import create_session_factory
from sysmind.infrastructure.database.repositories import (
    SqlAlchemyActionRepository,
    SqlAlchemyAgentTaskRepository,
    SqlAlchemyDiagnosisRepository,
    SqlAlchemyLogAnalysisRepository,
    SqlAlchemyScanRepository,
)
from sysmind.prompts import LocalReportExplainer
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


def create_agent_task_manager(database_url: str) -> AgentTaskManager:
    repository = SqlAlchemyAgentTaskRepository(create_session_factory(database_url))
    registry = build_runtime_registry(
        WindowsSystemProbe(),
        WindowsProcessProbe(),
        WindowsEventLogProbe(),
        WindowsNetworkProbe(),
        WindowsStartupProbe(),
        WindowsServiceProbe(),
    )
    return AgentTaskManager(repository, registry, FakeProvider)


def create_diagnosis_coordinator(database_url: str) -> DiagnosisCoordinator:
    repository = SqlAlchemyDiagnosisRepository(create_session_factory(database_url))
    registry = build_runtime_registry(
        WindowsSystemProbe(),
        WindowsProcessProbe(),
        WindowsEventLogProbe(),
        WindowsNetworkProbe(),
        WindowsStartupProbe(),
        WindowsServiceProbe(),
    )
    return DiagnosisCoordinator(repository, registry, LocalReportExplainer)


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
