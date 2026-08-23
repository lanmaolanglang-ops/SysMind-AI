# ADR-012: Reproducible Windows packaging and signed updates

- Status: Accepted
- Date: 2026-08-20

## Context

Phase 6 must run on Windows 10/11 x64 without a separately installed Python or Node runtime. The
desktop shell still owns exactly one loopback-only backend, database upgrades must run before API
readiness, and an update must not weaken the action, secret, or process-lifecycle boundaries from
earlier phases. The project does not own a signing certificate, update key, or public release URL in
source control.

## Decision

The Windows backend is frozen with PyInstaller as a one-directory application. Its Alembic
configuration and migration scripts are explicit bundle data. Tauri packages that directory as a
private application resource and resolves the bundled executable in release builds. Release builds
fail closed when the resource is absent; only debug builds may fall back to the developer-selected
Python interpreter. The existing random loopback port, environment-only session token, authenticated
health check, owned child handle, and Windows Job Object remain unchanged.

The desktop is a per-user NSIS application for Windows x64 and uses the official Tauri
single-instance and updater plugins. Update checks are user-visible and installation requires an
explicit click. Tauri verifies every update with its dedicated public update key before installation.
The update private key and Windows code-signing credentials are CI secrets. A formal release fails
when either signing mechanism is unavailable. Windows signs the frozen backend before it is embedded,
then Tauri signs the desktop executable and installer. Unsigned local packages are development
artifacts and cannot be promoted as releases.

Uninstall preserves `%LOCALAPPDATA%\ai.sysmind.desktop` by default. Tauri's interactive uninstaller
offers a separate opt-in deletion checkbox; silent uninstall and updater-driven replacement preserve it. Normal
startup runs all pending Alembic migrations. Downgrades are unsupported because migration history is
forward-only for releases.

The GitHub release workflow builds only from an explicit version tag, runs the ordinary quality
gates, creates the frozen backend and NSIS/update artifacts, and uploads them without ever writing
credentials to the workspace. The update endpoint uses the repository's stable latest-release URL,
while individual archive URLs remain pinned to the versioned tag and
the public update key is supplied as a non-secret release variable or secret at build time.

## Consequences

- A packaged installation has no Python or Node runtime dependency.
- One-directory freezing is larger than a one-file bootstrapper but avoids per-launch extraction and
  keeps migrations and native dependencies inspectable for signing and antivirus review.
- A certificate, timestamp service, update key pair, and public release repository are external
  release prerequisites; repository tests can verify the fail-closed configuration but cannot claim a
  production signature without them.
- Clean Windows 10/11 installation, upgrade, uninstall, antivirus, and signature verification remain
  release gates performed on disposable machines. They are not simulated on a developer workstation.
