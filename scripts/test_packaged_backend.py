from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import TextIO

HANDSHAKE_PREFIX = "SYSMIND_ENDPOINT "
HANDSHAKE_KEYS = {"event", "host", "port", "backend_version", "api_version"}


def read_line(stream: TextIO, output: queue.Queue[str]) -> None:
    for line in stream:
        output.put(line)


def request_json(url: str, token: str, method: str = "GET") -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=b"" if method != "GET" else None,
        method=method,
        headers={"X-SysMind-Session": token, "Origin": "tauri://localhost"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def validate_handshake(endpoint: object) -> int:
    if not isinstance(endpoint, dict) or set(endpoint) != HANDSHAKE_KEYS:
        raise RuntimeError("Packaged backend returned an invalid endpoint contract.")
    port = endpoint["port"]
    if (
        endpoint["event"] != "sysmind_endpoint"
        or endpoint["host"] != "127.0.0.1"
        or endpoint["api_version"] != "1.0"
        or not isinstance(endpoint["backend_version"], str)
        or not endpoint["backend_version"].strip()
        or type(port) is not int
        or not 1 <= port <= 65535
    ):
        raise RuntimeError("Packaged backend returned an invalid endpoint contract.")
    return port


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backend_directory", type=Path)
    args = parser.parse_args()
    executable = args.backend_directory.resolve() / "sysmind-backend.exe"
    if not executable.is_file():
        raise SystemExit(f"Packaged backend not found: {executable}")

    token = os.urandom(32).hex()
    environment = os.environ.copy()
    environment["SYSMIND_SESSION_TOKEN"] = token
    with tempfile.TemporaryDirectory(prefix="sysmind-package-test-") as temporary:
        data_dir = Path(temporary) / "data"
        process = subprocess.Popen(
            [
                str(executable),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--data-dir",
                str(data_dir),
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            # Not an `assert`: this is a runtime precondition that must survive `python -O`.
            if process.stdout is None:
                raise RuntimeError("Packaged backend stdout pipe was not available.")
            line_queue: queue.Queue[str] = queue.Queue()
            threading.Thread(
                target=read_line, args=(process.stdout, line_queue), daemon=True
            ).start()
            # Scan every stdout line for a handshake, matching product sidecar.rs
            # (`await_handshake`), which skips non-handshake lines rather than
            # requiring the handshake to be the first line.
            line = ""
            deadline = time.monotonic() + 20
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("Packaged backend handshake timed out.")
                try:
                    line = line_queue.get(timeout=remaining)
                except queue.Empty as error:
                    raise RuntimeError("Packaged backend handshake timed out.") from error
                if line.startswith(HANDSHAKE_PREFIX):
                    break
            endpoint = json.loads(line[len(HANDSHAKE_PREFIX) :])
            port = validate_handshake(endpoint)

            base_url = f"http://127.0.0.1:{port}"
            health = request_json(f"{base_url}/health", token)
            if health.get("status") != "ok" or health.get("ready") is not True:
                raise RuntimeError("Packaged backend was not ready.")
            request_json(f"{base_url}/internal/shutdown", token, method="POST")
            process.wait(timeout=5)
            if not (data_dir / "sysmind.db").is_file():
                raise RuntimeError("Packaged backend did not run its migrations.")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    print(f"Packaged backend smoke check passed: {executable}")


if __name__ == "__main__":
    main()
