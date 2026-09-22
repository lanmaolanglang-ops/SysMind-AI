from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from alembic import command
from sysmind.api.app import create_app
from sysmind.core.config import Settings
from sysmind.infrastructure.database import create_database_engine, run_migrations
from sysmind.infrastructure.database.migrations import alembic_config


def _current_head(config: Config) -> str:
    """Resolve the head revision from the migration scripts instead of hardcoding it."""
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head

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

    assert revision == _current_head(config)


def test_diagnosis_step_survives_its_tool_call_being_deleted(tmp_path: Path) -> None:
    """The step -> tool-call link is SET NULL, so a cascade never trip a foreign key."""
    database_url = f"sqlite:///{(tmp_path / 'fk.db').as_posix()}"
    run_migrations(database_url)
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO diagnoses "
                "(id, status, user_question, category, provider, plan_json, progress, "
                "agent_round_count, max_agent_rounds, max_tool_calls, created_at, schema_version) "
                "VALUES ('d-1', 'running', 'q', 'performance', 'p', '[]', 0, 0, 4, 8, "
                "'2026-09-10T00:00:00+00:00', '1.0')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO diagnosis_tool_calls "
                "(id, diagnosis_id, tool_name, tool_version, arguments_json, arguments_hash, "
                "status, started_at) VALUES ('c-1', 'd-1', 'system.cpu', '1.0', '{}', 'h', "
                "'completed', '2026-09-10T00:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO agent_plans "
                "(id, diagnosis_id, revision, provider, problem_category, confidence, status, "
                "plan_json, created_at) VALUES ('p-1', 'd-1', 1, 'p', 'performance', 0.5, "
                "'ready', '{}', '2026-09-10T00:00:00+00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO diagnosis_steps "
                "(id, plan_id, diagnosis_id, sequence, tool_name, tool_version, reason, "
                "arguments_hash, status, tool_call_id, created_at) "
                "VALUES ('s-1', 'p-1', 'd-1', 0, 'system.cpu', '1.0', 'r', 'h', 'completed', "
                "'c-1', '2026-09-10T00:00:00+00:00')"
            )
        )
        # Deleting the referenced tool call must null the link rather than fail.
        connection.execute(text("DELETE FROM diagnosis_tool_calls WHERE id = 'c-1'"))
        remaining = connection.execute(
            text("SELECT tool_call_id FROM diagnosis_steps WHERE id = 's-1'")
        ).scalar_one()

    assert remaining is None
    engine.dispose()
