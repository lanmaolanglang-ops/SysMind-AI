$ErrorActionPreference = "Stop"

$backendPython = Join-Path $PSScriptRoot "..\services\backend\.venv\Scripts\python.exe"
$backendBin = Join-Path $PSScriptRoot "..\services\backend\.venv\Scripts"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)] [scriptblock] $Command,
        [Parameter(Mandatory = $true)] [string] $Name
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $backendPython)) {
    throw "Backend virtual environment not found. Follow README.md setup first."
}

Invoke-Checked { & (Join-Path $backendBin "ruff.exe") check (Join-Path $PSScriptRoot "..\services\backend") } "Backend lint"
Invoke-Checked { & (Join-Path $backendBin "mypy.exe") (Join-Path $PSScriptRoot "..\services\backend\src") } "Backend typecheck"
Invoke-Checked { & (Join-Path $backendBin "pytest.exe") (Join-Path $PSScriptRoot "..\services\backend") } "Backend tests"
Invoke-Checked { pnpm lint } "Frontend lint"
Invoke-Checked { pnpm typecheck } "Frontend typecheck"
Invoke-Checked { pnpm test } "Frontend tests"
Invoke-Checked { pnpm build } "Frontend build"
Invoke-Checked { cargo fmt --manifest-path (Join-Path $PSScriptRoot "..\apps\desktop\src-tauri\Cargo.toml") --check } "Rust format"
Invoke-Checked { cargo test --manifest-path (Join-Path $PSScriptRoot "..\apps\desktop\src-tauri\Cargo.toml") } "Rust tests"
