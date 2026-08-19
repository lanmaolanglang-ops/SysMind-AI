# Phase 6 implementation checkpoint

Recorded: 2026-08-20

## Completed in the repository

- Accepted ADR-012 for PyInstaller one-directory freezing, Tauri private resources, per-user NSIS,
  fail-closed release inputs, signed updates, forward migrations, and preserve-by-default uninstall.
- Added a deterministic PyInstaller spec that includes Alembic configuration and every migration.
- Release Tauri builds resolve only the bundled backend (or an explicit test override); they never
  fall back to a machine-wide Python interpreter.
- Added official Tauri single-instance, process, and updater plugins with minimum capabilities.
- Added a user-visible update strip covering current, checking, available, installing, failure, and
  retry states. Installation is a separate explicit action and Tauri verifies the update signature.
- Enabled Windows x64 current-user NSIS packaging and the built-in opt-in app-data deletion checkbox.
- Added `scripts/package.ps1`, frozen-backend process-contract validation, checksums, legal resources,
  formal signing requirements, and a dual-gated disposable-VM installer runner.
- Added a protected GitHub draft-release workflow for Authenticode signing, Tauri updater signing,
  artifact verification, and publication.
- Added privacy, security, third-party licensing, release checklist, README, design-system, and
  integration-test documentation.

## Local verification

- Frozen `sysmind-backend.exe` started without system Python, ran Alembic to head, published an
  authenticated random-loopback endpoint, returned ready health, and shut down cleanly.
- Tauri produced an unsigned development NSIS installer with the backend and legal resources bundled.
- The packaged desktop started with the offline updater configuration, kept the session token out of
  process arguments, rejected a second instance without attempting a second sidecar, and terminated
  its owned sidecar on exit. After readiness was confirmed on loopback, a forced sidecar crash left
  the desktop alive without a false startup failure.
- Formal release mode rejected missing certificate/update-signing inputs before building.
- Backend Ruff and mypy passed; pytest passed with 90 tests and four intentionally skipped isolated
  mutation tests, including the new Phase 5-to-head migration round trip.
- Frontend ESLint, TypeScript, 25 Vitest tests, production build, and Impeccable UI detector passed.
- Rust formatting and four Rust tests passed. OpenAPI export and `git diff --check` passed.

## External release gates still required

Repository implementation is complete, but no production release can be claimed until the project
owner supplies a Windows code-signing certificate, Tauri update key pair, public release location,
private vulnerability-reporting route, and product distribution license. The signed artifacts and
clean Windows 10/11 VM matrix, upgrade from the prior release, interactive uninstall choices,
signature rejection, and antivirus review must then be executed and attached to the release using
`docs/release-checklist.md`. Phase 5 state-changing tests also remain restricted to a disposable VM.

The current acceptance host is Windows 11 Home and has neither Windows Sandbox nor a configured
GitHub remote/runner. Installer, uninstall, upgrade, signature-rejection, antivirus, and Phase 5
state-changing acceptance were therefore not executed on this workstation. The CI workflow includes
a dual-gated GitHub-hosted Windows package/installer job as the reproducible no-local-VM alternative;
it becomes executable after the repository is connected to GitHub.
