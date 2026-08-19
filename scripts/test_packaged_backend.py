from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import TextIO

HANDSHAKE_PREFIX = "SYSMIND_ENDPOINT "


def read_line(stream: TextIO, output: queue.Queue[str]) -> None:
    output.put(stream.readline())


def request_json(url: str, token: str, method: str = "GET") -> dict[str, object]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={"X-SysMind-Session": token, "Origin": "tauri://localhost"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


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
            assert process.stdout is not None
            line_queue: queue.Queue[str] = queue.Queue(maxsize=1)
            threading.Thread(target=read_line, args=(process.stdout, line_queue), daemon=True).start()
            try:
                line = line_queue.get(timeout=20)
            except queue.Empty as error:
                raise RuntimeError("Packaged backend handshake timed out.") from error
            if not line.startswith(HANDSHAKE_PREFIX):
                stderr = process.stderr.read() if process.poll() is not None and process.stderr else ""
                raise RuntimeError(f"Packaged backend did not return a handshake. {stderr}")
            endpoint = json.loads(line[len(HANDSHAKE_PREFIX) :])
            if endpoint.get("host") != "127.0.0.1" or endpoint.get("api_version") != "1.0":
                raise RuntimeError("Packaged backend returned an invalid endpoint contract.")

            base_url = f"http://127.0.0.1:{int(endpoint['port'])}"
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
