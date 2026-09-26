from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_PATH = REPOSITORY_ROOT / "contracts" / "versions.json"
CONSTANTS_PATH = (
    REPOSITORY_ROOT / "services" / "backend" / "src" / "sysmind" / "core" / "constants.py"
)
TS_VERSION_PATH = (
    REPOSITORY_ROOT / "apps" / "desktop" / "src" / "services" / "generated-version.ts"
)
RUST_VERSION_PATH = (
    REPOSITORY_ROOT / "apps" / "desktop" / "src-tauri" / "src" / "generated_version.rs"
)
TAURI_CONF_PATH = (
    REPOSITORY_ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
)
CARGO_TOML_PATH = REPOSITORY_ROOT / "apps" / "desktop" / "src-tauri" / "Cargo.toml"
BACKEND_PYPROJECT_PATH = REPOSITORY_ROOT / "services" / "backend" / "pyproject.toml"
DESKTOP_PACKAGE_PATH = REPOSITORY_ROOT / "apps" / "desktop" / "package.json"
ROOT_PACKAGE_PATH = REPOSITORY_ROOT / "package.json"


def load_versions() -> dict[str, str]:
    data = json.loads(VERSIONS_PATH.read_text(encoding="utf-8"))
    product = str(data["product_version"]).strip()
    api = str(data["api_version"]).strip()
    if not product or not api:
        raise SystemExit("contracts/versions.json must define product_version and api_version")
    return {"product_version": product, "api_version": api}


def constants_source(product: str, api: str) -> str:
    # Keep non-version constants in this file hand-maintained; only rewrite the
    # two version lines so sync-versions never drops SESSION/CORRELATION headers.
    current = read_text(CONSTANTS_PATH) if CONSTANTS_PATH.exists() else ""
    if not current:
        return (
            f'BACKEND_VERSION = "{product}"\n'
            f'API_VERSION = "{api}"\n'
            'LOOPBACK_HOST = "127.0.0.1"\n'
            'SESSION_HEADER = "X-SysMind-Session"\n'
            'CORRELATION_HEADER = "X-Correlation-ID"\n'
        )
    lines = current.splitlines(keepends=True)
    rewritten: list[str] = []
    seen_backend = False
    seen_api = False
    for line in lines:
        if line.startswith("BACKEND_VERSION"):
            rewritten.append(f'BACKEND_VERSION = "{product}"\n')
            seen_backend = True
        elif line.startswith("API_VERSION"):
            rewritten.append(f'API_VERSION = "{api}"\n')
            seen_api = True
        else:
            rewritten.append(line)
    if not seen_backend:
        rewritten.insert(0, f'BACKEND_VERSION = "{product}"\n')
    if not seen_api:
        rewritten.insert(1 if seen_backend else 0, f'API_VERSION = "{api}"\n')
    return "".join(rewritten)


def ts_source(product: str, api: str) -> str:
    return (
        "// Generated from contracts/versions.json by scripts/sync-versions.py.\n"
        f'export const PRODUCT_VERSION = "{product}";\n'
        f'export const EXPECTED_API_VERSION = "{api}";\n'
    )


def rust_source(product: str, api: str) -> str:
    return (
        "// Generated from contracts/versions.json by scripts/sync-versions.py.\n"
        "// PRODUCT_VERSION is consumed by packaging/updater paths; keep it exported\n"
        "// even when the current desktop build does not read it yet.\n"
        "#[allow(dead_code)]\n"
        f'pub const PRODUCT_VERSION: &str = "{product}";\n'
        f'pub const EXPECTED_API_VERSION: &str = "{api}";\n'
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def replace_package_version(text: str, product: str, label: str) -> str:
    updated, count = re.subn(
        r'^version = "[^"]+"$',
        f'version = "{product}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit(f"Could not find {label!r} while syncing versions.")
    return updated


def sync(check: bool) -> int:
    versions = load_versions()
    product = versions["product_version"]
    api = versions["api_version"]
    targets: dict[Path, str] = {
        CONSTANTS_PATH: constants_source(product, api),
        TS_VERSION_PATH: ts_source(product, api),
        RUST_VERSION_PATH: rust_source(product, api),
    }
    drifted: list[str] = []
    for path, expected in targets.items():
        current = read_text(path) if path.exists() else ""
        if current != expected:
            drifted.append(str(path.relative_to(REPOSITORY_ROOT)))
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(expected, encoding="utf-8", newline="\n")

    # Keep packaging manifests aligned with the single product version.
    tauri = json.loads(read_text(TAURI_CONF_PATH))
    if tauri.get("version") != product:
        drifted.append(str(TAURI_CONF_PATH.relative_to(REPOSITORY_ROOT)))
        if not check:
            tauri["version"] = product
            TAURI_CONF_PATH.write_text(
                json.dumps(tauri, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    cargo = read_text(CARGO_TOML_PATH)
    if f'version = "{product}"' not in cargo.split("[dependencies]", 1)[0]:
        drifted.append(str(CARGO_TOML_PATH.relative_to(REPOSITORY_ROOT)))
        if not check:
            cargo = replace_package_version(cargo, product, "Cargo.toml package version")
            CARGO_TOML_PATH.write_text(cargo, encoding="utf-8", newline="\n")

    pyproject = read_text(BACKEND_PYPROJECT_PATH)
    if f'version = "{product}"' not in pyproject:
        drifted.append(str(BACKEND_PYPROJECT_PATH.relative_to(REPOSITORY_ROOT)))
        if not check:
            pyproject = replace_package_version(pyproject, product, "pyproject package version")
            BACKEND_PYPROJECT_PATH.write_text(pyproject, encoding="utf-8", newline="\n")

    for package_path in (DESKTOP_PACKAGE_PATH, ROOT_PACKAGE_PATH):
        package = json.loads(read_text(package_path))
        if package.get("version") != product:
            drifted.append(str(package_path.relative_to(REPOSITORY_ROOT)))
            if not check:
                package["version"] = product
                package_path.write_text(
                    json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )

    if drifted:
        if check:
            print("Version drift detected:", file=sys.stderr)
            for item in drifted:
                print(f"  - {item}", file=sys.stderr)
            print("Run: python scripts/sync-versions.py", file=sys.stderr)
            return 1
        for item in drifted:
            print(f"updated {item}")
    else:
        print("versions already in sync")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when generated files or packaging manifests drift from versions.json",
    )
    args = parser.parse_args()
    raise SystemExit(sync(check=bool(args.check)))


if __name__ == "__main__":
    main()
