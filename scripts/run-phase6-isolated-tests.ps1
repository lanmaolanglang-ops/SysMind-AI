[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [switch]$ConfirmIsolatedEnvironment
)

$ErrorActionPreference = 'Stop'
$marker = 'C:\SysMind-Isolated-Test-VM.marker'
$isSandbox = $env:USERNAME -eq 'WDAGUtilityAccount'
$isMarkedVm = Test-Path -LiteralPath $marker -PathType Leaf
$isGitHubHosted = $env:GITHUB_ACTIONS -eq 'true' -and $env:RUNNER_ENVIRONMENT -eq 'github-hosted'
if (-not $ConfirmIsolatedEnvironment -or (-not $isSandbox -and -not $isMarkedVm -and -not $isGitHubHosted)) {
    throw 'Refusing installer tests: run in Windows Sandbox, a marked disposable VM, or a GitHub-hosted runner, and pass -ConfirmIsolatedEnvironment.'
}

$installer = (Resolve-Path -LiteralPath $InstallerPath).Path
$dataDirectory = Join-Path $env:LOCALAPPDATA 'ai.sysmind.desktop'
$sentinel = Join-Path $dataDirectory 'phase6-preserve-sentinel.txt'

$install = Start-Process -FilePath $installer -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
if ($install.ExitCode -ne 0) { throw "Silent install failed with exit code $($install.ExitCode)." }

$application = Join-Path $env:LOCALAPPDATA 'SysMind AI\sysmind-desktop.exe'
if (-not (Test-Path -LiteralPath $application -PathType Leaf)) {
    $application = Get-ChildItem -LiteralPath $env:LOCALAPPDATA -Filter 'sysmind-desktop.exe' -File -Recurse |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $application) { throw 'Installed desktop executable was not found.' }

New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
Set-Content -LiteralPath $sentinel -Value 'preserve-on-silent-uninstall' -Encoding utf8
$appProcess = Start-Process -FilePath $application -PassThru
Start-Sleep -Seconds 5
if ($appProcess.HasExited) { throw 'Installed application exited during startup.' }
Stop-Process -Id $appProcess.Id -ErrorAction SilentlyContinue

$uninstaller = Get-ChildItem -LiteralPath (Split-Path -Parent $application) -Filter 'uninstall.exe' -File | Select-Object -First 1
if (-not $uninstaller) { throw 'Installed uninstaller was not found.' }
$uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
if ($uninstall.ExitCode -ne 0) { throw "Silent uninstall failed with exit code $($uninstall.ExitCode)." }
if (-not (Test-Path -LiteralPath $sentinel -PathType Leaf)) {
    throw 'Silent uninstall removed user data instead of preserving it.'
}

Write-Output 'Phase 6 isolated install, launch, and preserve-on-uninstall checks passed.'
