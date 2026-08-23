from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from alembic import command
from sysmind.api.app import create_app
from sysmind.core.config import Settings
from sysmind.infrastructure.database import create_database_engine, run_migrations
from sysmind.infrastructure.database.migrations import alembic_config

CURRENT_TABLES = {
    "app_metadata",
    "system_scans",
    "scan_step_events",
    "event_log_analyses",
    "event_log_step_events",
    "agent_tasks",
    "agent_task_events",
    "agent_tool_calls",
    "agent_model_calls",
    "diagnoses",
    "diagnosis_tool_calls",
    "diagnosis_feedback",
    "diagnosis_model_calls",
    "agent_plans",
    "diagnosis_steps",
    "agent_decisions",
    "task_user_inputs",
    "diagnosis_hypotheses",
    "agent_stop_reasons",
}


def test_app_shutdown_releases_the_sqlite_file(settings: Settings) -> None:
    database_path = settings.data_dir / "sysmind.db"

    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 401
        assert database_path.is_file()

    moved_path = settings.data_dir / "sysmind-after-shutdown.db"
    database_path.rename(moved_path)
    moved_path.rename(database_path)


def test_database_initialization_enables_safety_pragmas(settings: Settings) -> None:
    run_migrations(settings.database_url)
    engine = create_database_engine(settings.database_url)

    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()

    assert foreign_keys == 1
    assert str(journal_mode).lower() == "wal"
    assert CURRENT_TABLES.issubset(inspect(engine).get_table_names())
    engine.dispose()


def test_current_migrations_upgrade_phase1_without_losing_scan_history(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    command.upgrade(alembic_config(database_url), "0002_phase1")
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO system_scans "
                "(id, scan_type, status, progress, started_at, failures_json, schema_version) "
                "VALUES ('phase1-record', 'quick', 'completed', 100, "
                "'2026-08-19T10:00:00+00:00', '[]', '1.0')"
            )
        )
    engine.dispose()

    run_migrations(database_url)
    engine = create_database_engine(database_url)

    assert CURRENT_TABLES.issubset(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM system_scans WHERE id = 'phase1-record'")
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_current_migrations_round_trip_from_phase5(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'phase5-upgrade.db').as_posix()}"
    config = alembic_config(database_url)

    command.upgrade(config, "0005_phase4")
    command.upgrade(config, "head")
    command.downgrade(config, "0005_phase4")
    command.upgrade(config, "head")

    engine = create_database_engine(database_url)
    with engine.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    engine.dispose()

    assert revision == "0010_phase32"
