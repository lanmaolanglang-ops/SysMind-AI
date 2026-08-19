from __future__ import annotations

import argparse

from pydantic import SecretStr

from sysmind.core.config import Settings
from sysmind.runtime.server import report_startup_failure, run_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SysMind AI local backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--session-token")
    parser.add_argument("--data-dir")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.data_dir and args.session_token:
        settings = Settings(
            host=args.host,
            port=args.port,
            session_token=SecretStr(args.session_token),
            data_dir=args.data_dir,
        )
    elif args.data_dir:
        settings = Settings(
            host=args.host,
            port=args.port,
            data_dir=args.data_dir,
        )
    elif args.session_token:
        settings = Settings(
            host=args.host,
            port=args.port,
            session_token=SecretStr(args.session_token),
        )
    else:
        settings = Settings(host=args.host, port=args.port)
    try:
        run_server(settings)
    except BaseException as error:
        report_startup_failure(error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
