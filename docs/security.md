# SysMind AI security model

Last updated: 2026-08-20

## Trust boundaries

- The ordinary-user Tauri process owns one frozen FastAPI child process. The child listens only on
  `127.0.0.1`, chooses a random port, and requires an environment-only per-launch session token plus an
  allowed Origin.
- On Windows the backend is assigned to a Job Object with `KILL_ON_JOB_CLOSE`; shutdown first uses the
  authenticated local endpoint and may terminate only the retained child handle.
- The AI model cannot call Win32, Shell, PowerShell, CMD, or arbitrary commands. It can select only
  versioned read-only tools admitted by the Tool Registry and policy engine.
- State-changing actions remain outside that registry. They require evidence-bound application plans,
  short-lived parameter-bound single-use confirmation, fresh target validation, audit, and post-state
  verification.

## Release integrity

- PyInstaller creates an inspectable one-directory backend. Alembic assets are bundled explicitly and
  migrations run before readiness.
- Formal releases sign the backend, desktop executable, and NSIS installer with a Windows code-signing
  certificate and timestamp. The certificate and password are CI secrets and are never committed.
- Tauri updater artifacts use a separate asymmetric update key. The public key is compiled into the
  release configuration; the private key remains in the release environment. Update verification
  cannot be disabled.
- The updater uses HTTPS, installs only after explicit user action, and preserves the current
  installation when checking, downloading, signature verification, or installation fails.
- Release builds fail if the frozen backend or required signing inputs are missing. Unsigned local
  packages are development artifacts, not releases.

## Supported release boundary

Phase 6 targets Windows 10/11 x64 and per-user installation. It adds no administrator helper, service
control, arbitrary file deletion, generic registry writes, network changes, or command execution.
Downgrades are unsupported because database migrations are forward-only.

## Vulnerability handling

Do not include API keys, session tokens, unredacted logs, or personal diagnostic exports in a report.
Until a public security contact is established, use the repository host's private security-advisory
channel. Public release is blocked if no private reporting channel is configured.
