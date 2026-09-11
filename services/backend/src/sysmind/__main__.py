from __future__ import annotations

import argparse

from sysmind.core.config import Settings, configure_settings
from sysmind.runtime.server import report_startup_failure, run_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SysMind AI local backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--data-dir")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.data_dir:
        settings = Settings(
            host=args.host,
            port=args.port,
            data_dir=args.data_dir,
        )
    else:
        settings = Settings(host=args.host, port=args.port)
    # Bind the process-wide settings before anything can call get_settings(), so the
    # randomly generated session token is created exactly once per process.
    configure_settings(settings)
    try:
        run_server(settings)
    except BaseException as error:
        report_startup_failure(error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
