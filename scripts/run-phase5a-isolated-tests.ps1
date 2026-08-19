[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [switch]$ConfirmIsolatedEnvironment
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$marker = 'C:\SysMind-Isolated-Test-VM.marker'
$isSandbox = $env:USERNAME -eq 'WDAGUtilityAccount'
$isMarkedVm = Test-Path -LiteralPath $marker -PathType Leaf

if (-not $ConfirmIsolatedEnvironment -or (-not $isSandbox -and -not $isMarkedVm)) {
    throw 'Refusing state-changing tests: run in Windows Sandbox or a disposable VM containing C:\SysMind-Isolated-Test-VM.marker, and pass -ConfirmIsolatedEnvironment.'
}

$python = Join-Path $workspace 'services\backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'The backend virtual environment is unavailable in this isolated machine.'
}

$env:SYSMIND_DESTRUCTIVE_SANDBOX = 'SYSMIND_PHASE5A_ISOLATED_TEST_ONLY'
try {
    & $python -m pytest `
        (Join-Path $workspace 'services\backend\tests\test_phase5a_windows_sandbox.py') `
        -m destructive_sandbox -vv
    if ($LASTEXITCODE -ne 0) {
        throw "Phase 5 isolated tests failed with exit code $LASTEXITCODE."
    }
}
finally {
    Remove-Item Env:SYSMIND_DESTRUCTIVE_SANDBOX -ErrorAction SilentlyContinue
}
