[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$')]
    [string]$Version = '0.1.0',
    [switch]$Release,
    [switch]$SkipChecks,
    [string]$UpdaterPublicKey = $env:SYSMIND_UPDATER_PUBLIC_KEY,
    [string]$UpdaterEndpoint = $env:SYSMIND_UPDATER_ENDPOINT,
    [string]$ReleaseBaseUrl = $env:SYSMIND_RELEASE_BASE_URL,
    [string]$CertificateThumbprint = $env:SYSMIND_WINDOWS_CERTIFICATE_THUMBPRINT,
    [string]$TimestampUrl = 'http://timestamp.digicert.com'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
# Windows PowerShell 5.1 does not define $IsWindows; StrictMode would fail the check below.
if (-not (Test-Path variable:IsWindows)) {
    Set-Variable -Name IsWindows -Value $true -Scope Global -Force
}
if (-not $IsWindows -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'Phase 6 packages must be built on Windows x64.'
}

$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRoot = Join-Path $workspace 'services\backend'
$desktopRoot = Join-Path $workspace 'apps\desktop'
$tauriRoot = Join-Path $desktopRoot 'src-tauri'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$packagingRoot = Join-Path $backendRoot 'packaging'
$distRoot = Join-Path $packagingRoot 'dist'
$workRoot = Join-Path $packagingRoot 'build'
$sidecarDirectory = Join-Path $distRoot 'sysmind-backend'
$sidecarExecutable = Join-Path $sidecarDirectory 'sysmind-backend.exe'
$packageRoot = Join-Path $tauriRoot 'target\phase6-package'
$overlayPath = Join-Path $packageRoot 'tauri.release.conf.json'

function Reset-BuildDirectory([string]$Path, [string]$AllowedRoot) {
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\') + '\'
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear build path outside $resolvedRoot"
    }
    if (Test-Path -LiteralPath $resolvedPath) {
        Remove-Item -LiteralPath $resolvedPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $resolvedPath -Force | Out-Null
}

function Find-SignTool {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $candidate = Get-ChildItem -LiteralPath $kitsRoot -Filter signtool.exe -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if (-not $candidate) { throw 'signtool.exe was not found in PATH or the Windows SDK.' }
    return $candidate.FullName
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Backend virtual environment is missing. Install services/backend[dev,packaging] first.'
}

$backendVersion = (& $python -c 'from sysmind.core.constants import BACKEND_VERSION; print(BACKEND_VERSION)').Trim()
$tauriConfig = Get-Content -LiteralPath (Join-Path $tauriRoot 'tauri.conf.json') -Raw | ConvertFrom-Json
$cargoVersion = (Select-String -LiteralPath (Join-Path $tauriRoot 'Cargo.toml') -Pattern '^version = "(.+)"$' | Select-Object -First 1).Matches.Groups[1].Value
if ($backendVersion -ne $Version -or $tauriConfig.version -ne $Version -or $cargoVersion -ne $Version) {
    throw "Version mismatch: requested=$Version backend=$backendVersion tauri=$($tauriConfig.version) cargo=$cargoVersion"
}

if ($Release) {
    $missing = @()
    if (-not $UpdaterPublicKey) { $missing += 'SYSMIND_UPDATER_PUBLIC_KEY' }
    if (-not $UpdaterEndpoint) { $missing += 'SYSMIND_UPDATER_ENDPOINT' }
    if (-not $ReleaseBaseUrl) { $missing += 'SYSMIND_RELEASE_BASE_URL' }
    if (-not $CertificateThumbprint) { $missing += 'SYSMIND_WINDOWS_CERTIFICATE_THUMBPRINT' }
    if (-not $env:TAURI_SIGNING_PRIVATE_KEY) { $missing += 'TAURI_SIGNING_PRIVATE_KEY' }
    if ($missing.Count -gt 0) {
        throw "Release signing inputs are missing: $($missing -join ', ')"
    }
}

if (-not $SkipChecks) {
    & (Join-Path $workspace 'scripts\check.ps1')
}

Reset-BuildDirectory -Path $distRoot -AllowedRoot $packagingRoot
Reset-BuildDirectory -Path $workRoot -AllowedRoot $packagingRoot
Reset-BuildDirectory -Path $packageRoot -AllowedRoot (Join-Path $tauriRoot 'target')

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $distRoot `
    --workpath $workRoot `
    (Join-Path $packagingRoot 'sysmind-backend.spec')
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sidecarExecutable -PathType Leaf)) {
    throw 'PyInstaller did not produce the expected one-directory backend.'
}

& $python (Join-Path $workspace 'scripts\test_packaged_backend.py') $sidecarDirectory
if ($LASTEXITCODE -ne 0) { throw 'Packaged backend smoke check failed.' }

if ($Release) {
    $signTool = Find-SignTool
    & $signTool sign /sha1 $CertificateThumbprint /fd SHA256 /td SHA256 /tr $TimestampUrl $sidecarExecutable
    if ($LASTEXITCODE -ne 0) { throw 'Windows signing failed for the frozen backend.' }
    & $signTool verify /pa /all $sidecarExecutable
    if ($LASTEXITCODE -ne 0) { throw 'Windows signature verification failed for the frozen backend.' }
}

$resources = @{}
$resources[$sidecarDirectory] = 'backend'
$resources[(Join-Path $workspace 'docs\privacy.md')] = 'legal/privacy.md'
$resources[(Join-Path $workspace 'docs\security.md')] = 'legal/security.md'
$resources[(Join-Path $workspace 'docs\third-party-licenses.md')] = 'legal/third-party-licenses.md'
$overlay = [ordered]@{
    version = $Version
    bundle = [ordered]@{
        resources = $resources
        createUpdaterArtifacts = [bool]$Release
    }
}
if ($Release) {
    $overlay.bundle.windows = [ordered]@{
        certificateThumbprint = $CertificateThumbprint
        digestAlgorithm = 'sha256'
        timestampUrl = $TimestampUrl
    }
    $overlay.plugins = [ordered]@{
        updater = [ordered]@{
            pubkey = $UpdaterPublicKey
            endpoints = @($UpdaterEndpoint)
            windows = [ordered]@{ installMode = 'passive' }
        }
    }
}
$overlay | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $overlayPath -Encoding utf8

Push-Location $desktopRoot
$previousUpdaterAvailability = $env:VITE_SYSMIND_UPDATER_AVAILABLE
try {
    $env:VITE_SYSMIND_UPDATER_AVAILABLE = if ($Release) { 'true' } else { 'false' }
    pnpm exec tauri build --config $overlayPath
    if ($LASTEXITCODE -ne 0) { throw "Tauri bundle failed with exit code $LASTEXITCODE." }
}
finally {
    if ($null -eq $previousUpdaterAvailability) {
        Remove-Item Env:VITE_SYSMIND_UPDATER_AVAILABLE -ErrorAction SilentlyContinue
    }
    else {
        $env:VITE_SYSMIND_UPDATER_AVAILABLE = $previousUpdaterAvailability
    }
    Pop-Location
}

& $python (Join-Path $workspace 'scripts\test_packaged_desktop.py') `
    (Join-Path $tauriRoot 'target\release\sysmind-desktop.exe')
if ($LASTEXITCODE -ne 0) { throw 'Packaged desktop lifecycle check failed.' }

$bundleRoot = Join-Path $tauriRoot 'target\release\bundle\nsis'
$installer = Get-ChildItem -LiteralPath $bundleRoot -Filter '*-setup.exe' -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if (-not $installer) { throw 'Tauri did not produce an NSIS installer.' }

$artifactFiles = @($installer)
if ($Release) {
    $updateArchive = Get-ChildItem -LiteralPath $bundleRoot -Filter '*.nsis.zip' -File | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if (-not $updateArchive -or -not (Test-Path -LiteralPath ($updateArchive.FullName + '.sig') -PathType Leaf)) {
        throw 'Tauri did not produce signed updater artifacts.'
    }
    $signature = (Get-Content -LiteralPath ($updateArchive.FullName + '.sig') -Raw).Trim()
    $latest = [ordered]@{
        version = $Version
        notes = "SysMind AI $Version"
        pub_date = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
        platforms = [ordered]@{
            'windows-x86_64' = [ordered]@{
                signature = $signature
                url = $ReleaseBaseUrl.TrimEnd('/') + '/' + $updateArchive.Name
            }
        }
    }
    $latestPath = Join-Path $bundleRoot 'latest.json'
    $latest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $latestPath -Encoding utf8
    $artifactFiles += $updateArchive
    $artifactFiles += Get-Item -LiteralPath ($updateArchive.FullName + '.sig')
    $artifactFiles += Get-Item -LiteralPath $latestPath
}

$checksums = foreach ($artifact in $artifactFiles) {
    $hash = Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256
    [ordered]@{ file = $artifact.Name; sha256 = $hash.Hash.ToLowerInvariant() }
}
$checksumPath = Join-Path $bundleRoot 'SHA256SUMS.json'
ConvertTo-Json -InputObject @($checksums) -Depth 4 | Set-Content -LiteralPath $checksumPath -Encoding utf8

Write-Output "Package created: $($installer.FullName)"
Write-Output "Checksums: $checksumPath"
