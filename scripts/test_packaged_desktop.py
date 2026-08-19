from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

import psutil

WM_CLOSE = 0x0010


def backend_children(desktop_pid: int) -> list[psutil.Process]:
    try:
        children = psutil.Process(desktop_pid).children(recursive=True)
    except psutil.Error:
        return []
    return [child for child in children if child.name().lower() == "sysmind-backend.exe"]


def wait_for_backend(desktop_pid: int, timeout: float = 20) -> psutil.Process:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        children = backend_children(desktop_pid)
        if len(children) == 1:
            return children[0]
        if len(children) > 1:
            raise RuntimeError("Packaged desktop created more than one backend.")
        time.sleep(0.1)
    raise RuntimeError("Packaged desktop did not start its bundled backend.")


def wait_for_backend_ready(process: psutil.Process, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            connections = process.net_connections(kind="tcp")
        except psutil.Error as error:
            raise RuntimeError("Could not inspect the packaged backend endpoint.") from error
        if any(
            connection.status == psutil.CONN_LISTEN
            and connection.laddr.ip == "127.0.0.1"
            and connection.laddr.port > 0
            for connection in connections
        ):
            return
        time.sleep(0.1)
    raise RuntimeError("Packaged backend did not become ready on a loopback endpoint.")


def close_visible_windows(process_id: int) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def close_if_owned(window: int, _parameter: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == process_id and user32.IsWindowVisible(window):
            user32.PostMessageW(window, WM_CLOSE, 0, 0)
        return True

    if not user32.EnumWindows(callback_type(close_if_owned), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def launch(executable: Path, data_directory: Path) -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    environment["SYSMIND_DATA_DIR"] = str(data_directory)
    environment.pop("SYSMIND_PYTHON", None)
    environment.pop("SYSMIND_BACKEND_EXECUTABLE", None)
    return subprocess.Popen(
        [str(executable)],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def read_stderr(process: subprocess.Popen[bytes]) -> str:
    if process.stderr is None:
        return ""
    return process.stderr.read().decode(errors="replace")


def stop_desktop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    close_visible_windows(process.pid)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("desktop_executable", type=Path)
    args = parser.parse_args()
    executable = args.desktop_executable.resolve()
    if not executable.is_file():
        raise SystemExit(f"Packaged desktop not found: {executable}")

    results: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="sysmind-desktop-test-") as temporary:
        data_directory = Path(temporary) / "data"

        desktop = launch(executable, data_directory)
        backend = wait_for_backend(desktop.pid)
        wait_for_backend_ready(backend)
        try:
            command_line = backend.cmdline()
            results["bundled_backend_started"] = True
            results["session_token_not_in_arguments"] = "--session-token" not in command_line

            second = launch(executable, data_directory)
            try:
                second.wait(timeout=10)
            except subprocess.TimeoutExpired as error:
                second.kill()
                raise RuntimeError("Second desktop instance did not exit.") from error
            second_stderr = read_stderr(second)
            results["second_instance_exited"] = True
            results["second_instance_did_not_attempt_backend_start"] = (
                "backend lifecycle error" not in second_stderr.lower()
            )
            results["single_backend_after_second_launch"] = len(backend_children(desktop.pid)) == 1
        finally:
            backend_pid = backend.pid
            stop_desktop(desktop)
        desktop_stderr = read_stderr(desktop)
        results["primary_instance_had_no_backend_start_error"] = (
            "could not start the python sidecar" not in desktop_stderr.lower()
        )
        deadline = time.monotonic() + 5
        while psutil.pid_exists(backend_pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        results["owned_backend_exited_with_desktop"] = not psutil.pid_exists(backend_pid)

        crash_desktop = launch(executable, data_directory)
        crash_backend = wait_for_backend(crash_desktop.pid)
        wait_for_backend_ready(crash_backend)
        try:
            crash_backend.kill()
            crash_backend.wait(timeout=5)
            time.sleep(1)
            results["desktop_survived_backend_crash"] = crash_desktop.poll() is None
        finally:
            stop_desktop(crash_desktop)
        crash_stderr = read_stderr(crash_desktop)
        results["crash_scenario_had_no_backend_start_error"] = (
            "could not start the python sidecar" not in crash_stderr.lower()
        )

    failed = [name for name, passed in results.items() if not passed]
    print(json.dumps(results, indent=2, sort_keys=True))
    if failed:
        if desktop_stderr:
            print(f"Primary desktop stderr:\n{desktop_stderr}", file=sys.stderr)
        if crash_stderr:
            print(f"Crash scenario stderr:\n{crash_stderr}", file=sys.stderr)
        raise RuntimeError(f"Packaged desktop checks failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
