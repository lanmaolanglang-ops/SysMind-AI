from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from sysmind.infrastructure.database.migrations import alembic_config, migration_assets_root


def _packaging_script():
    script_path = Path(__file__).parents[3] / "scripts" / "test_packaged_backend.py"
    spec = spec_from_file_location("test_packaged_backend_script", script_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_packaged_backend_handshake_contract_is_exact() -> None:
    script = _packaging_script()
    endpoint = {
        "event": "sysmind_endpoint",
        "host": "127.0.0.1",
        "port": 54321,
        "backend_version": "0.1.0",
        "api_version": "1.0",
    }

    assert script.validate_handshake(endpoint) == 54321

    with pytest.raises(RuntimeError, match="invalid endpoint contract"):
        script.validate_handshake({**endpoint, "unexpected": True})
    with pytest.raises(RuntimeError, match="invalid endpoint contract"):
        script.validate_handshake({**endpoint, "port": True})
    with pytest.raises(RuntimeError, match="invalid endpoint contract"):
        script.validate_handshake({**endpoint, "backend_version": ""})
