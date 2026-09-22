from __future__ import annotations

"""Generate TypeScript types from the exported OpenAPI contract.

The OpenAPI document is the single source of truth for API response shapes.
This generator is intentionally small (no extra npm toolchain) and only covers
the JSON Schema subset FastAPI emits for this project.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = REPOSITORY_ROOT / "contracts" / "openapi" / "sysmind-local-api.json"
OUTPUT_PATH = REPOSITORY_ROOT / "apps" / "desktop" / "src" / "services" / "openapi-types.ts"

HEADER = """/* Generated from contracts/openapi/sysmind-local-api.json by scripts/generate-ts-types.py.
 * Do not edit by hand. Run: python scripts/generate-ts-types.py
 */

export type components = {
  schemas: {
"""


def ts_type(schema: dict[str, Any], schemas: dict[str, Any], indent: str) -> str:
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return f"components['schemas']['{name}']"
    if "anyOf" in schema:
        parts = [ts_type(item, schemas, indent) for item in schema["anyOf"] if item.get("type") != "null"]
        if not parts:
            return "unknown"
        return " | ".join(parts)
    if "allOf" in schema:
        parts = [ts_type(item, schemas, indent) for item in schema["allOf"]]
        return " & ".join(parts)
    if "enum" in schema:
        return " | ".join(json.dumps(item) for item in schema["enum"])
    kind = schema.get("type")
    if kind == "string":
        return "string"
    if kind == "integer" or kind == "number":
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "null":
        return "null"
    if kind == "array":
        item = schema.get("items", {})
        return f"Array<{ts_type(item, schemas, indent)}>"
    if kind == "object" or "properties" in schema or "additionalProperties" in schema:
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        if not props:
            additional = schema.get("additionalProperties")
            if additional is True:
                return "Record<string, unknown>"
            if isinstance(additional, dict):
                return f"Record<string, {ts_type(additional, schemas, indent)}>"
            return "Record<string, unknown>"
        lines = ["{"]
        for key, value in props.items():
            optional = "" if key in required else "?"
            key_text = json.dumps(key) if not key.isidentifier() else key
            lines.append(f"{indent}  {key_text}{optional}: {ts_type(value, schemas, indent + '  ')};")
        lines.append(f"{indent}}}")
        return "\n".join(lines)
    return "unknown"


def render_schema(name: str, schema: dict[str, Any], schemas: dict[str, Any]) -> str:
    body = ts_type(schema, schemas, "    ")
    if body.startswith("{"):
        return f"    {name}: {body}\n"
    return f"    {name}: {body};\n"


def generate() -> str:
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas = document.get("components", {}).get("schemas", {})
    parts = [HEADER]
    for name in sorted(schemas):
        parts.append(render_schema(name, schemas[name], schemas))
    parts.append("  };\n};\n")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = generate()
    current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
    if current != expected:
        if args.check:
            print(
                "OpenAPI TypeScript types are stale. Run: python scripts/generate-ts-types.py",
                file=sys.stderr,
            )
            raise SystemExit(1)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(expected, encoding="utf-8", newline="\n")
        print(OUTPUT_PATH)
    else:
        print("openapi-types.ts already up to date")


if __name__ == "__main__":
    main()
