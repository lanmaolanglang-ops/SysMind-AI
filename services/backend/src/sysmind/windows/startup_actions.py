from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, cast

from sysmind.domain.actions import MutationResult, StartupActionCandidate
from sysmind.tools.contracts import ToolPermissionError, ToolUnavailableError

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REPARSE_POINT = 0x400


class TargetChangedError(RuntimeError):
    pass


def _digest(*parts: object) -> str:
    return hashlib.sha256("\0".join(str(part) for part in parts).encode()).hexdigest()


def _basename(command: str) -> str | None:
    text = command.strip()
    if not text:
        return None
    executable = (
        text.split('"', 2)[1] if text.startswith('"') and '"' in text[1:] else text.split()[0]
    )
    return Path(executable).name or None


class WindowsStartupActionAdapter:
    def __init__(self, recovery_root: Path) -> None:
        self._root = recovery_root.resolve()

    def candidates(self) -> tuple[StartupActionCandidate, ...]:
        if os.name != "nt":
            raise ToolUnavailableError("Windows startup actions are unavailable.")
        import winreg

        found: list[StartupActionCandidate] = []
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                for index in range(min(winreg.QueryInfoKey(key)[1], 100)):
                    name, value, value_type = winreg.EnumValue(key, index)
                    found.append(
                        StartupActionCandidate(
                            _digest("user_run", name),
                            name,
                            "user_run",
                            _basename(str(value)),
                            _digest("user_run", name, value_type, value),
                        )
                    )
        except OSError:
            pass
        folder = self._startup_folder()
        try:
            for entry in list(folder.iterdir())[:100]:
                if self._safe_file(entry, folder):
                    stat = entry.stat()
                    found.append(
                        StartupActionCandidate(
                            _digest("user_startup", entry.name),
                            entry.stem,
                            "user_startup",
                            entry.name,
                            _digest("user_startup", entry.name, stat.st_size, stat.st_mtime_ns),
                        )
                    )
        except OSError:
            pass
        return tuple(found)

    def disable(self, item_id: str, observed_revision: str) -> MutationResult:
        candidate = next((item for item in self.candidates() if item.item_id == item_id), None)
        if candidate is None or candidate.observed_revision != observed_revision:
            raise TargetChangedError("Startup target changed after confirmation.")
        recovery_id = str(uuid.uuid4())
        directory = self._recovery_directory(recovery_id, create=True)
        metadata: dict[str, object]
        if candidate.source_kind == "user_run":
            import winreg

            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    _RUN_KEY,
                    0,
                    winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
                ) as key:
                    value, value_type = winreg.QueryValueEx(key, candidate.name)
                    if _digest("user_run", candidate.name, value_type, value) != observed_revision:
                        raise TargetChangedError("Startup target changed after confirmation.")
                    metadata = {
                        "kind": "user_run",
                        "name": candidate.name,
                        "value": value,
                        "value_type": value_type,
                    }
                    self._write_metadata(directory, metadata)
                    winreg.DeleteValue(key, candidate.name)
            except PermissionError as error:
                raise ToolPermissionError(
                    "Current-user startup entry could not be changed."
                ) from error
            except OSError as error:
                raise TargetChangedError("Startup target is no longer available.") from error
        else:
            folder = self._startup_folder()
            source = folder / str(candidate.command_name)
            if not self._safe_file(source, folder):
                raise TargetChangedError("Startup file identity changed.")
            stat = source.stat()
            if (
                _digest("user_startup", source.name, stat.st_size, stat.st_mtime_ns)
                != observed_revision
            ):
                raise TargetChangedError("Startup file changed after confirmation.")
            metadata = {"kind": "user_startup", "name": source.name}
            self._write_metadata(directory, metadata)
            shutil.move(str(source), str(directory / "item"))
        if any(item.item_id == item_id for item in self.candidates()):
            raise ToolUnavailableError("Startup action could not be verified.")
        return MutationResult(recovery_id, None)

    def restore(self, recovery_id: str) -> MutationResult:
        directory = self._recovery_directory(recovery_id)
        metadata = self._read_metadata(directory)
        kind, name = metadata.get("kind"), metadata.get("name")
        if not isinstance(name, str) or kind not in {"user_run", "user_startup"}:
            raise TargetChangedError("Recovery record is invalid.")
        item_id = _digest(kind, name)
        if any(item.item_id == item_id for item in self.candidates()):
            raise TargetChangedError("Startup target slot is already occupied.")
        if kind == "user_run":
            import winreg

            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.SetValueEx(
                        key,
                        name,
                        0,
                        int(cast(Any, metadata["value_type"])),
                        cast(Any, metadata["value"]),
                    )
            except (OSError, KeyError, TypeError) as error:
                raise ToolPermissionError(
                    "Current-user startup entry could not be restored."
                ) from error
        else:
            folder = self._startup_folder()
            destination = folder / name
            if destination.exists() or not self._inside(destination, folder):
                raise TargetChangedError("Startup target slot is no longer safe.")
            shutil.move(str(directory / "item"), str(destination))
        restored = next((item for item in self.candidates() if item.item_id == item_id), None)
        if restored is None:
            raise ToolUnavailableError("Startup recovery could not be verified.")
        shutil.rmtree(directory)
        return MutationResult(None, restored.observed_revision)

    def recovery_exists(self, recovery_id: str) -> bool:
        try:
            return (self._recovery_directory(recovery_id) / "metadata.json").is_file()
        except ValueError:
            return False

    @staticmethod
    def _startup_folder() -> Path:
        appdata = os.getenv("APPDATA")
        if not appdata:
            raise ToolUnavailableError("Current-user Startup folder is unavailable.")
        return (Path(appdata) / "Microsoft/Windows/Start Menu/Programs/Startup").resolve()

    @staticmethod
    def _inside(path: Path, root: Path) -> bool:
        try:
            return os.path.commonpath((str(path.resolve(strict=False)), str(root))) == str(root)
        except (OSError, ValueError):
            return False

    def _safe_file(self, path: Path, root: Path) -> bool:
        try:
            stat = path.lstat()
            return (
                self._inside(path, root)
                and path.is_file()
                and not path.is_symlink()
                and not stat.st_file_attributes & _REPARSE_POINT
            )
        except (OSError, AttributeError):
            return False

    def _recovery_directory(self, recovery_id: str, *, create: bool = False) -> Path:
        if not recovery_id or any(char not in "0123456789abcdef-" for char in recovery_id.lower()):
            raise ValueError("Invalid recovery identifier.")
        directory = (self._root / recovery_id).resolve()
        if not self._inside(directory, self._root):
            raise ValueError("Invalid recovery identifier.")
        if create:
            directory.mkdir(parents=True, exist_ok=False)
        return directory

    @staticmethod
    def _write_metadata(directory: Path, metadata: dict[str, object]) -> None:
        (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    @staticmethod
    def _read_metadata(directory: Path) -> dict[str, object]:
        try:
            data = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise TargetChangedError("Recovery record is unavailable.") from error
