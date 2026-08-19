from pathlib import Path

from alembic.config import Config

from alembic import command


def alembic_config(database_url: str) -> Config:
    backend_root = Path(__file__).resolve().parents[4]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def run_migrations(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
