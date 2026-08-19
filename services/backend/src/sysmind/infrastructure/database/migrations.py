import sys
from pathlib import Path

from alembic.config import Config

from alembic import command


def migration_assets_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if isinstance(frozen_root, str):
        return Path(frozen_root)
    return Path(__file__).resolve().parents[4]


def alembic_config(database_url: str) -> Config:
    assets_root = migration_assets_root()
    config = Config(str(assets_root / "alembic.ini"))
    config.set_main_option("script_location", str(assets_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def run_migrations(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
