from sysmind.application.services import QuickScanCoordinator
from sysmind.infrastructure.database import create_session_factory
from sysmind.infrastructure.database.repositories import SqlAlchemyScanRepository
from sysmind.tools.process import ProcessTools
from sysmind.tools.system import SystemTools
from sysmind.windows import WindowsProcessProbe, WindowsSystemProbe


def create_quick_scan_coordinator(database_url: str) -> QuickScanCoordinator:
    repository = SqlAlchemyScanRepository(create_session_factory(database_url))
    return QuickScanCoordinator(
        repository,
        SystemTools(WindowsSystemProbe()),
        ProcessTools(WindowsProcessProbe()),
    )
