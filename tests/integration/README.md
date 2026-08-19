# Desktop integration and Phase 1 Windows smoke checks

These checks exercise Tauri and the Python sidecar together and are intentionally separate from unit tests.

## Automated coverage already present

- Python verifies loopback random-port binding and explicit port conflicts.
- Python verifies authenticated health, Origin rejection, migration startup, and graceful shutdown signaling.
- TypeScript verifies API version mismatch, launcher startup failure, retry UI, and API error normalization.
- Rust verifies endpoint handshake parsing and protocol mismatch detection.
- The UI restart action calls Tauri's owned-process restart command rather than only polling stale state.
- Python exercises normalized Windows collectors and a real authenticated quick-scan API on Windows.

## Manual Windows smoke test

1. Create and activate `services/backend/.venv`; install `.[dev]`.
2. Set `SYSMIND_PYTHON` to the absolute virtual-environment Python executable.
   Optionally set `SYSMIND_DATA_DIR` to an absolute disposable test directory.
3. Run `pnpm desktop` from the repository root.
4. Confirm the UI transitions from **Backend Starting** to **Backend Connected**.
5. Confirm the displayed network boundary is `127.0.0.1`.
6. Start a quick scan and verify progress identifies the current collector.
7. Verify the result shows Windows, CPU, memory, GPU, disks, and a process observation count; unavailable items must appear as partial warnings rather than erase successful results.
8. Start another scan, cancel it, and verify the terminal state is “扫描已取消”.
9. Close the window and verify no child `sysmind` Python process remains.
10. Set `SYSMIND_PYTHON` to a missing executable, restart, and confirm a recoverable disconnected state is shown.
11. Start the backend manually with an occupied `--port`; confirm it exits without binding another interface.

An end-to-end process harness can replace these manual steps once the frozen sidecar artifact exists in Phase 6.
# Phase 5 state-changing Windows checks

Phase 5 startup and process mutation tests must never run on a normal development machine. Use a
disposable Windows VM snapshot with Python dependencies installed, then create the empty marker
`C:\SysMind-Isolated-Test-VM.marker`. Windows Sandbox is also accepted when the workspace and its
backend virtual environment are available inside the sandbox.

From the isolated guest only:

```powershell
Set-Location 'D:\SysMind AI'
.\scripts\run-phase5a-isolated-tests.ps1 -ConfirmIsolatedEnvironment
```

The runner requires both the command-line acknowledgement and either the Windows Sandbox account or
the VM marker. The tests create only uniquely named `SysMindPhase5ATest-*` entries and disposable test
processes. They verify stale revision refusal, disable/restore, occupied-slot recovery refusal,
bounded `WM_CLOSE`, pending close, double-confirmed fixed `TerminateProcess`, post-state verification,
and cleanup. The default pytest command skips this marker and does not change system state.

# Phase 6 packaged-install checks

`scripts/package.ps1` performs a non-destructive frozen-backend smoke check before creating an NSIS
installer. It verifies that the packaged executable can run migrations, bind a random loopback port,
authenticate health, and shut down without using the system Python installation.

Installation and uninstallation change Windows application state and therefore run only in Windows
Sandbox or a disposable marked VM:

```powershell
.\scripts\run-phase6-isolated-tests.ps1 `
  -InstallerPath '<path-to-SysMind-AI-setup.exe>' `
  -ConfirmIsolatedEnvironment
```

The automated isolated runner installs silently, launches the packaged desktop, and verifies that a
silent uninstall preserves local application data. The remaining interactive, upgrade, signature,
antivirus, Windows 10/11, and bad-update-signature cases are recorded in
`docs/release-checklist.md` and require saved VM/release evidence.
