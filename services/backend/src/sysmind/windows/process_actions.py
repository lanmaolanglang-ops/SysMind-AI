from __future__ import annotations

import ctypes
import hashlib
import os
import time
from ctypes import wintypes
from pathlib import Path

import psutil

from sysmind.domain.actions import MutationResult, ProcessActionCandidate
from sysmind.tools.contracts import ToolUnavailableError
from sysmind.windows.startup_actions import TargetChangedError

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_TERMINATE = 0x0001
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_TOKEN_ELEVATION_TYPE = 18
_TOKEN_ELEVATION_TYPE_FULL = 2
_WM_CLOSE = 0x0010
_GW_OWNER = 4
_PROTECTED_NAMES = {
    "system",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "winlogon.exe",
    "dwm.exe",
    "fontdrvhost.exe",
    "sihost.exe",
    "taskhostw.exe",
    "explorer.exe",
    "taskmgr.exe",
    "applicationframehost.exe",
    "textinputhost.exe",
    "systemsettings.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "searchhost.exe",
    "securityhealthsystray.exe",
    "securityhealthservice.exe",
}
_PROTECTED_NAME_FRAGMENTS = ("antivirus", "defender", "endpoint", "security", "edr")


class _SidAndAttributes(ctypes.Structure):
    _fields_ = (("sid", ctypes.c_void_p), ("attributes", wintypes.DWORD))


class _TokenUser(ctypes.Structure):
    _fields_ = (("user", _SidAndAttributes),)


def _digest(*parts: object) -> str:
    return hashlib.sha256("\0".join(str(part) for part in parts).encode()).hexdigest()


class WindowsProcessActionAdapter:
    def __init__(self, *, close_wait_seconds: float = 8.0) -> None:
        if not 0.1 <= close_wait_seconds <= 8.0:
            raise ValueError("Close verification wait must be between 0.1 and 8 seconds.")
        self._wait = close_wait_seconds

    def candidates(self) -> tuple[ProcessActionCandidate, ...]:
        if os.name != "nt":
            raise ToolUnavailableError("Windows process actions are unavailable.")
        current_sid = self._process_sid(os.getpid())
        current_session = self._session_id(os.getpid())
        current_elevation = self._elevation_type(os.getpid())
        protected_pids = self._sysmind_process_tree()
        windows = self._visible_windows()
        candidates: list[ProcessActionCandidate] = []
        for process in psutil.process_iter(("pid", "name", "create_time", "exe")):
            pid = process.pid
            try:
                name = str(process.info.get("name") or "")
                handles = windows.get(pid, ())
                if (
                    not handles
                    or pid in protected_pids
                    or name.casefold() in _PROTECTED_NAMES
                    or any(fragment in name.casefold() for fragment in _PROTECTED_NAME_FRAGMENTS)
                    or "sysmind" in name.casefold()
                    or self._is_critical(pid)
                    or self._session_id(pid) != current_session
                    or self._process_sid(pid) != current_sid
                    or (
                        self._elevation_type(pid) == _TOKEN_ELEVATION_TYPE_FULL
                        and current_elevation != _TOKEN_ELEVATION_TYPE_FULL
                    )
                ):
                    continue
                created = float(process.info["create_time"])
                image = str(process.info.get("exe") or "").casefold()
                memory = round(process.memory_percent(), 2)
                cpu = round(process.cpu_percent(interval=None), 1)
                item_id = _digest("current_user_process", pid, created)
                revision = _digest(pid, created, current_sid, current_session, image, *handles)
                candidates.append(
                    ProcessActionCandidate(
                        item_id,
                        name or f"PID {pid}",
                        "current_user_process",
                        Path(image).name or None,
                        revision,
                        pid,
                        cpu,
                        memory,
                    )
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, OSError):
                continue
        return tuple(candidates[:50])

    def request_close(self, item_id: str, observed_revision: str) -> MutationResult:
        candidate = next((item for item in self.candidates() if item.item_id == item_id), None)
        if candidate is None or candidate.observed_revision != observed_revision:
            raise TargetChangedError("Process identity changed after confirmation.")
        handles = self._visible_windows().get(candidate.pid, ())
        if not handles:
            raise TargetChangedError("Process no longer owns an eligible visible window.")
        user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.PostMessageW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.PostMessageW.restype = wintypes.BOOL
        for handle in handles:
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(wintypes.HWND(handle), ctypes.byref(owner))
            if owner.value != candidate.pid:
                raise TargetChangedError("Window ownership changed after confirmation.")
            if not user32.PostMessageW(wintypes.HWND(handle), _WM_CLOSE, 0, 0):
                raise ToolUnavailableError("Windows rejected the bounded close request.")
        deadline = time.monotonic() + self._wait
        while time.monotonic() < deadline:
            if not self._same_process(candidate):
                return MutationResult(None, None, "closed")
            time.sleep(0.1)
        return MutationResult(None, candidate.observed_revision, "close_pending")

    def terminate(self, item_id: str, observed_revision: str) -> MutationResult:
        candidate = next((item for item in self.candidates() if item.item_id == item_id), None)
        if candidate is None or candidate.observed_revision != observed_revision:
            raise TargetChangedError("Process identity changed after double confirmation.")
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(
            _PROCESS_TERMINATE | _PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            candidate.pid,
        )
        if not handle:
            raise TargetChangedError("Process is no longer an eligible termination target.")
        try:
            if not kernel32.TerminateProcess(handle, 0x53594D):
                raise ToolUnavailableError("Windows rejected the bounded termination request.")
        finally:
            kernel32.CloseHandle(handle)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if not self._same_process(candidate):
                return MutationResult(None, None, "terminated")
            time.sleep(0.05)
        raise ToolUnavailableError("Process termination could not be verified.")

    def _same_process(self, candidate: ProcessActionCandidate) -> bool:
        try:
            process = psutil.Process(candidate.pid)
            return (
                _digest("current_user_process", candidate.pid, process.create_time())
                == candidate.item_id
            )
        except psutil.AccessDenied as error:
            raise ToolUnavailableError(
                "Process identity could not be verified after execution."
            ) from error
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False

    @staticmethod
    def _visible_windows() -> dict[int, tuple[int, ...]]:
        user32 = ctypes.WinDLL("user32.dll", use_last_error=True)
        found: dict[int, list[int]] = {}
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
        user32.GetWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

        @callback_type  # type: ignore[untyped-decorator]
        def collect(handle: int, _parameter: int) -> bool:
            if (
                user32.IsWindowVisible(handle)
                and not user32.GetWindow(handle, _GW_OWNER)
                and user32.GetWindowTextLengthW(handle) > 0
            ):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
                if pid.value:
                    found.setdefault(pid.value, []).append(int(handle))
            return True

        user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
        user32.EnumWindows.restype = wintypes.BOOL
        if not user32.EnumWindows(collect, 0):
            raise ToolUnavailableError("Windows could not enumerate eligible application windows.")
        return {pid: tuple(sorted(handles)) for pid, handles in found.items()}

    @staticmethod
    def _session_id(pid: int) -> int:
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.ProcessIdToSessionId.argtypes = (
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
        session = wintypes.DWORD()
        if not kernel32.ProcessIdToSessionId(pid, ctypes.byref(session)):
            raise OSError("Session identity is unavailable.")
        return int(session.value)

    @staticmethod
    def _process_sid(pid: int) -> str:
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
        kernel32.LocalFree.restype = ctypes.c_void_p
        advapi32.OpenProcessToken.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        )
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        )
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.ConvertSidToStringSidW.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        )
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            raise OSError("Process identity is unavailable.")
        token = wintypes.HANDLE()
        try:
            if not advapi32.OpenProcessToken(handle, _TOKEN_QUERY, ctypes.byref(token)):
                raise OSError("Process token is unavailable.")
            size = wintypes.DWORD()
            advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
            buffer = ctypes.create_string_buffer(size.value)
            if not advapi32.GetTokenInformation(
                token, _TOKEN_USER, buffer, size, ctypes.byref(size)
            ):
                raise OSError("Process user SID is unavailable.")
            user = ctypes.cast(buffer, ctypes.POINTER(_TokenUser)).contents
            text = ctypes.c_wchar_p()
            if not advapi32.ConvertSidToStringSidW(user.user.sid, ctypes.byref(text)):
                raise OSError("Process user SID is unavailable.")
            try:
                return str(text.value)
            finally:
                kernel32.LocalFree(ctypes.cast(text, ctypes.c_void_p))
        finally:
            if token:
                kernel32.CloseHandle(token)
            kernel32.CloseHandle(handle)

    @staticmethod
    def _is_critical(pid: int) -> bool:
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return True
        try:
            critical = wintypes.BOOL()
            function = getattr(kernel32, "IsProcessCritical", None)
            if function is None:
                return True
            function.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
            function.restype = wintypes.BOOL
            return not function(handle, ctypes.byref(critical)) or bool(critical)
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _elevation_type(pid: int) -> int:
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        advapi32 = ctypes.WinDLL("advapi32.dll", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        advapi32.OpenProcessToken.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        )
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        )
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        process = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not process:
            raise OSError("Process elevation is unavailable.")
        token = wintypes.HANDLE()
        try:
            if not advapi32.OpenProcessToken(process, _TOKEN_QUERY, ctypes.byref(token)):
                raise OSError("Process elevation is unavailable.")
            elevation = wintypes.DWORD()
            size = wintypes.DWORD()
            if not advapi32.GetTokenInformation(
                token,
                _TOKEN_ELEVATION_TYPE,
                ctypes.byref(elevation),
                ctypes.sizeof(elevation),
                ctypes.byref(size),
            ):
                raise OSError("Process elevation is unavailable.")
            return int(elevation.value)
        finally:
            if token:
                kernel32.CloseHandle(token)
            kernel32.CloseHandle(process)

    @staticmethod
    def _sysmind_process_tree() -> set[int]:
        current = psutil.Process()
        protected = {current.pid}
        try:
            protected.update(process.pid for process in current.parents())
            protected.update(process.pid for process in current.children(recursive=True))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
        return protected
