from __future__ import annotations

import sys
from pathlib import Path

from sysmind.infrastructure.database.migrations import alembic_config, migration_assets_root


def test_source_migration_assets_are_resolved() -> None:
    root = migration_assets_root()

    assert (root / "alembic.ini").is_file()
    assert (root / "alembic" / "env.py").is_file()


def test_frozen_migration_assets_are_resolved(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    config = alembic_config("sqlite:///C:/Temp/sysmind.db")

    assert migration_assets_root() == tmp_path
    assert config.config_file_name == str(tmp_path / "alembic.ini")
    assert config.get_main_option("script_location") == str(tmp_path / "alembic")
