from pathlib import Path

from sqlalchemy import inspect, text

from sysmind.core.config import Settings
from sysmind.infrastructure.database import create_database_engine, run_migrations


def test_database_initialization_enables_safety_pragmas(settings: Settings) -> None:
    run_migrations(settings.database_url)
    engine = create_database_engine(settings.database_url)

    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()

    assert foreign_keys == 1
    assert str(journal_mode).lower() == "wal"
    assert "app_metadata" in inspect(engine).get_table_names()
    engine.dispose()


def test_migration_can_upgrade_and_downgrade(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'migration.db').as_posix()}"
    run_migrations(database_url)
    engine = create_database_engine(database_url)

    assert "app_metadata" in inspect(engine).get_table_names()
    engine.dispose()

