# Phase 6 Windows release checklist

No build is a production release until every required item below has evidence attached to the draft
release. Unsigned local installers are development artifacts.

## Current preflight evidence (2026-08-23)

- [x] Frozen backend process contract and migration-to-head smoke test passed.
- [x] Packaged desktop portable lifecycle passed: loopback readiness, no token in arguments,
  single-instance/no second sidecar attempt, owned-sidecar cleanup, and desktop survival after a
  ready sidecar was forcibly terminated.
- [x] Unsigned NSIS development installer was generated and checksummed.
- [x] GitHub-hosted Windows CI passed backend, frontend, frozen-backend/Rust smoke, unsigned NSIS
  packaging, portable lifecycle, and the dual-gated silent install/launch/uninstall-preserve flow on
  commit `0e9d5ec`.
- [x] RC2 exercised the final unsigned Local Validation Build on one Windows 11 x64 device: real
  read-only diagnosis tools, fresh-data startup, bundled-backend lifecycle, single instance, forced
  backend failure visibility, silent install, and data-preserving silent uninstall.
- [x] RC2 quality gates recorded backend 145 passed / 4 isolated state-change tests skipped,
  frontend 34 passed, Rust 5 passed, and Alembic head `0010_phase32`.
- [ ] The current Windows 11 Home workstation still has no Windows Sandbox. Phase 5 state-changing
  checks and the remaining manual release matrix below must use a disposable VM or equivalent
  isolated runner; do not substitute the normal workstation.

## Source and version

- [ ] Release commit is reviewed and the working tree contains no unintended files or secrets.
- [ ] Git tag, backend version, Cargo version, and Tauri version are the same SemVer.
- [ ] Backend Ruff, mypy, pytest; frontend lint, typecheck, Vitest, production build; Rust format and
  tests all pass.
- [ ] Alembic current-head upgrade and supported previous-release upgrade are verified on copied data.
- [ ] OpenAPI contract is regenerated and reviewed when API code changed.

## Signing and artifacts

- [ ] Windows certificate is current, trusted, and available only in the protected release environment.
- [ ] Frozen backend, desktop executable, and NSIS installer have valid timestamped Authenticode
  signatures.
- [ ] Tauri update public key matches the protected private key and the prior release channel.
- [ ] `latest.json`, updater archive/signature, installer, and `SHA256SUMS.json` refer to the same version.
- [ ] Dependency licenses and notices are reviewed; the project owner has declared the product's own
  distribution license.
- [ ] Installer and extracted binaries are scanned by the selected antivirus/multi-engine service;
  detections are investigated rather than bypassed.

## Disposable Windows validation

- [ ] Clean Windows 10 x64 VM without Python or Node: install, launch, diagnose offline, close, and
  verify no backend remains.
- [ ] Clean Windows 11 x64 VM without Python or Node: repeat the same flow.
- [ ] Standard-user installation succeeds without UAC; administrator-account launch does not silently
  broaden the application's permissions.
- [ ] Second desktop launch focuses the existing instance and does not create a second sidecar.
- [ ] Forced backend crash is visible and the user can restart the owned backend without orphaning a
  process.
- [ ] Upgrade from the last supported release preserves data, runs migrations, and retains readable
  history and action audit records.
- [ ] Update with a bad signature is rejected; offline/timeout update checks leave the current version
  usable.
- [ ] Silent uninstall preserves `%LOCALAPPDATA%\ai.sysmind.desktop`; interactive uninstall verifies
  both “preserve” and explicit “delete” choices from a VM snapshot.
- [ ] Phase 5 isolated startup and process-action tests pass in a disposable VM; never run them on a
  normal workstation.

## Publication

- [ ] Privacy, security, third-party license, release notes, and private vulnerability-reporting route
  are available to users.
- [ ] Draft release download URLs are tested over HTTPS before the draft is published.
- [ ] Roll-forward response is prepared. Database downgrade is not supported and must not be suggested
  as recovery.
