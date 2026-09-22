from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, cast

from sysmind.application.ports.actions import ActionVerificationError, TargetChangedError
from sysmind.domain.actions import MutationResult, StartupActionCandidate
from sysmind.security.redaction import redact_secrets
from sysmind.tools.contracts import ToolPermissionError, ToolUnavailableError
from sysmind.windows.identity import opaque_item_id, startup_item_id
from sysmind.windows.platform_inspection import _basename

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REPARSE_POINT = 0x400


def _digest(*parts: object) -> str:
    return opaque_item_id(*parts)


# Recovery metadata is read back from disk and its `name` is reused as a Run key
# value name and as a Startup folder file name. Anything that can write the
# recovery directory would otherwise choose that name, so keep it to what a real
# startup entry can be: bounded, printable, and free of path/wildcard characters.
_MAX_ENTRY_NAME_LENGTH = 255
_FORBIDDEN_ENTRY_NAME_CHARS = frozenset('\\/:*?"<>|')
# Windows reserved device names, also reserved with an extension ("NUL.txt").
_WINDOWS_RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def _require_safe_entry_name(name: str) -> str:
    if not 1 <= len(name) <= _MAX_ENTRY_NAME_LENGTH:
        raise TargetChangedError("Recovery record is invalid.")
    if any(char in _FORBIDDEN_ENTRY_NAME_CHARS or ord(char) < 32 for char in name):
        raise TargetChangedError("Recovery record is invalid.")
    stem = name.split(".", 1)[0].rstrip(" ").upper()
    if stem in _WINDOWS_RESERVED_DEVICE_NAMES:
        raise TargetChangedError("Recovery record is invalid.")
    return name


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
                            startup_item_id("user_run", name),
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
                            startup_item_id("user_startup", entry.name),
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
                    # Recovery metadata lives on disk. The Run command line is required
                    # to restore the registry value, so it cannot be dropped or hashed
                    # away; encryption of recovery material is out of scope. At least
                    # strip credential-looking substrings (password=/token=/Bearer/…)
                    # so a recovery directory never holds plaintext secrets. Full
                    # redact_text is deliberately NOT applied here: it would mangle
                    # user-profile paths and break restore.
                    if isinstance(value, str):
                        safe_value: object = redact_secrets(value)
                        value_digest = hashlib.sha256(
                            cast(str, safe_value).encode("utf-8")
                        ).hexdigest()
                    else:
                        safe_value = value
                        value_digest = None
                    metadata = {
                        "kind": "user_run",
                        "name": candidate.name,
                        "value": safe_value,
                        "value_type": value_type,
                        # Digest of the value as stored at disable time. Restore
                        # refuses to write a payload that no longer matches.
                        "value_digest": value_digest,
                    }
                    self._write_metadata(directory, metadata)
                    winreg.DeleteValue(key, candidate.name)
            except PermissionError as error:
                shutil.rmtree(directory, ignore_errors=True)
                raise ToolPermissionError(
                    "Current-user startup entry could not be changed."
                ) from error
            except OSError as error:
                shutil.rmtree(directory, ignore_errors=True)
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
            try:
                self._write_metadata(directory, metadata)
                shutil.move(str(source), str(directory / "item"))
            except OSError:
                shutil.rmtree(directory, ignore_errors=True)
                raise
        if any(item.item_id == item_id for item in self.candidates()):
            raise ActionVerificationError(
                "Startup action could not be verified.", recovery_id=recovery_id
            )
        return MutationResult(recovery_id, None)

    def restore(self, recovery_id: str) -> MutationResult:
        directory = self._recovery_directory(recovery_id)
        metadata = self._read_metadata(directory)
        kind, name = metadata.get("kind"), metadata.get("name")
        if not isinstance(name, str) or kind not in {"user_run", "user_startup"}:
            raise TargetChangedError("Recovery record is invalid.")
        _require_safe_entry_name(name)
        item_id = startup_item_id(kind, name)
        if any(item.item_id == item_id for item in self.candidates()):
            raise TargetChangedError("Startup target slot is already occupied.")
        if kind == "user_run":
            import winreg

            stored_value = cast(Any, metadata.get("value"))
            stored_digest = metadata.get("value_digest")
            # When the disable-time digest is present, require the restore payload to
            # still match it (metadata.json integrity). Absent digest keeps older
            # recovery records restorable.
            if stored_digest is not None and (
                not isinstance(stored_value, str)
                or hashlib.sha256(stored_value.encode("utf-8")).hexdigest() != stored_digest
            ):
                raise TargetChangedError("Recovery record value was changed.")
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.SetValueEx(
                        key,
                        name,
                        0,
                        int(cast(Any, metadata["value_type"])),
                        stored_value,
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
            raise ActionVerificationError("Startup recovery could not be verified.")
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
