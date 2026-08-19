from __future__ import annotations

import json
import socket
import sys

import uvicorn

from sysmind.api.app import create_app
from sysmind.core.config import Settings
from sysmind.core.constants import API_VERSION, BACKEND_VERSION, LOOPBACK_HOST
from sysmind.runtime.shutdown import ShutdownController


def bind_loopback(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((LOOPBACK_HOST, port))
        listener.listen(2048)
        listener.set_inheritable(True)
        return listener
    except BaseException:
        listener.close()
        raise


def run_server(settings: Settings) -> None:
    listener = bind_loopback(settings.port)
    actual_port = int(listener.getsockname()[1])
    controller = ShutdownController()
    app = create_app(settings, controller)
    config = uvicorn.Config(
        app,
        host=LOOPBACK_HOST,
        port=actual_port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    controller.set_callback(lambda: setattr(server, "should_exit", True))

    handshake = {
        "event": "sysmind_endpoint",
        "host": LOOPBACK_HOST,
        "port": actual_port,
        "backend_version": BACKEND_VERSION,
        "api_version": API_VERSION,
    }
    print(f"SYSMIND_ENDPOINT {json.dumps(handshake, separators=(',', ':'))}", flush=True)
    server.run(sockets=[listener])


def report_startup_failure(error: BaseException) -> None:
    payload = {
        "event": "sysmind_startup_error",
        "code": type(error).__name__,
        "message": str(error),
    }
    print(
        f"SYSMIND_ERROR {json.dumps(payload, separators=(',', ':'))}",
        file=sys.stderr,
        flush=True,
    )
