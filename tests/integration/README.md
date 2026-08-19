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
