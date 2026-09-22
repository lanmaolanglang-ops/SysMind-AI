from __future__ import annotations

import json
import secrets
from pathlib import Path

from pydantic import SecretStr

from sysmind.api.app import create_app
from sysmind.core.config import Settings


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    target = repository_root / "contracts" / "openapi" / "sysmind-local-api.json"
    settings = Settings(
        data_dir=repository_root / ".sysmind-data" / "openapi",
        # The OpenAPI document does not depend on the token value; generate a throwaway one
        # so no literal credential ever lives in source control.
        session_token=SecretStr(secrets.token_urlsafe(32)),
    )
    document = create_app(settings).openapi()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
