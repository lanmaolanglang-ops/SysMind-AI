# ADR-002: Tauri owns a Python sidecar

- Status: Accepted
- Date: 2026-08-19

## Context

Tauri supplies the Windows desktop lifecycle while Python provides the planned diagnostic and AI ecosystem. The backend must remain local, discoverable without a fixed port, and unable to outlive its owning app unnoticed.

## Decision

Tauri starts one FastAPI sidecar on `127.0.0.1` with port `0` and a fresh session token. The token is inherited through the child environment rather than exposed in command-line arguments. Python binds the socket and emits one structured endpoint handshake. Tauri waits for authenticated `/health`, retains the exact child handle, and exposes endpoint data to the frontend only in memory.

Development uses `SYSMIND_PYTHON -m sysmind`. The launcher can instead use `SYSMIND_BACKEND_EXECUTABLE`, which is the seam for a frozen executable. On Windows the child is placed in a Job Object with `KILL_ON_JOB_CLOSE`. Normal exit requests `/internal/shutdown`, waits two seconds, then may terminate only the retained child.

## Consequences

There is no fixed-port collision during normal startup and no public network listener. Process management code is Windows-sensitive and needs smoke tests. The stdout handshake is a versioned process contract, not a general logging channel.
