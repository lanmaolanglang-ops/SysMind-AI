$ErrorActionPreference = "Stop"

$backendPython = Join-Path $PSScriptRoot "..\services\backend\.venv\Scripts\python.exe"
$backendBin = Join-Path $PSScriptRoot "..\services\backend\.venv\Scripts"

if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend virtual environment not found. Follow README.md setup first."
}

& (Join-Path $backendBin "ruff.exe") check (Join-Path $PSScriptRoot "..\services\backend")
& (Join-Path $backendBin "mypy.exe") (Join-Path $PSScriptRoot "..\services\backend\src")
& (Join-Path $backendBin "pytest.exe") (Join-Path $PSScriptRoot "..\services\backend")
pnpm lint
pnpm typecheck
pnpm test
pnpm build
cargo fmt --manifest-path (Join-Path $PSScriptRoot "..\apps\desktop\src-tauri\Cargo.toml") --check
cargo test --manifest-path (Join-Path $PSScriptRoot "..\apps\desktop\src-tauri\Cargo.toml")

