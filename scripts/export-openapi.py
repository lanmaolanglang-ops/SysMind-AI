from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import SecretStr
from sysmind.api.app import create_app
from sysmind.core.config import Settings


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    target = repository_root / "contracts" / "openapi" / "sysmind-local-api.json"
    settings = Settings(
        data_dir=repository_root / ".sysmind-data" / "openapi",
        session_token=SecretStr("contract-generation-session-token"),
    )
    document = create_app(settings).openapi()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, ensure_ascii=False) + os.linesep, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
