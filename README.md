# SysMind AI

SysMind AI is a local-first Windows desktop foundation for an explainable computer diagnostic assistant. Phase 0 contains the desktop shell, authenticated local backend lifecycle, persistence foundation, and test/CI scaffolding. It does **not** inspect the computer, call an AI model, or change system state.

The product and architecture baseline is [docs/SysMind-AI-PRD-and-Architecture.md](docs/SysMind-AI-PRD-and-Architecture.md).

## Architecture at a glance

```text
React + TypeScript UI
        │ Tauri invoke (endpoint discovery)
        │ REST over 127.0.0.1 + ephemeral session token
        ▼
Tauri 2 process owner ───── starts/stops ───── Python FastAPI sidecar
                                                    │
                                                    ▼
                                          SQLAlchemy 2 + SQLite
                                          Alembic migrations
```

The Tauri process owns the exact child process it creates. On Windows, the child is assigned to a Job Object with `KILL_ON_JOB_CLOSE`; normal exit first requests graceful backend shutdown and only terminates that owned child after a timeout. A development launcher uses Python today and the same abstraction accepts a frozen executable later.

## Phase 0 safety boundary

- The backend host is a validated literal `127.0.0.1`; `0.0.0.0` is rejected.
- Every API request requires an ephemeral `X-SysMind-Session` token.
- Browser/Tauri origins are allowlisted and correlation IDs cross the API boundary.
- API keys are not implemented or persisted. `FakeSecretService` is memory-only.
- Logs are structured JSON and redact common secret fields.
- No system diagnostics, Agent, model provider, arbitrary command, or repair behavior exists.

## Development requirements

- Windows 10/11 x64
- Node.js 22 or later and pnpm 10 or later
- Python 3.11 or later
- Rust stable with the MSVC Windows toolchain
- Microsoft WebView2 Runtime and the Windows SDK required by Tauri 2

The examples below use PowerShell from the repository root.

## Initial setup

```powershell
pnpm install

python -m venv services/backend/.venv
& services/backend/.venv/Scripts/python.exe -m pip install --upgrade pip
& services/backend/.venv/Scripts/python.exe -m pip install -e "services/backend[dev]"
```

No `.env` file is required. Never put real API keys in repository environment files.

## Run the backend alone

```powershell
$token = "development-session-token-change-me-0001"
& services/backend/.venv/Scripts/python.exe -m sysmind `
  --host 127.0.0.1 `
  --port 0 `
  --session-token $token `
  --data-dir .sysmind-data
```

The first stdout handshake begins with `SYSMIND_ENDPOINT` and includes the randomly assigned loopback port. Call `/health` with `X-SysMind-Session`; do not paste session tokens into issue reports or logs.

## Run the web UI only

```powershell
pnpm dev
```

The UI expects the Tauri command bridge and therefore shows a disconnected state in a normal browser. This is expected.

## Run the desktop application

```powershell
$env:SYSMIND_PYTHON = (Resolve-Path "services/backend/.venv/Scripts/python.exe")
pnpm desktop
```

Tauri starts Vite, launches the Python module with a random port and an inherited environment-only token, waits for authenticated `/health`, then exposes the endpoint to the frontend in process memory.

Tests or portable development environments may set `SYSMIND_DATA_DIR` to an absolute disposable directory. Normal application runs leave it unset and use Tauri's Windows application-data directory.

## Tests and quality checks

Backend:

```powershell
& services/backend/.venv/Scripts/ruff.exe check services/backend
& services/backend/.venv/Scripts/mypy.exe services/backend/src
& services/backend/.venv/Scripts/pytest.exe services/backend
```

Frontend:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Tauri/Rust:

```powershell
cargo fmt --manifest-path apps/desktop/src-tauri/Cargo.toml --check
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
```

Manual lifecycle checks are documented in [tests/integration/README.md](tests/integration/README.md).

## Directory guide

```text
apps/desktop/              React/Vite UI and Tauri 2 shell
services/backend/          FastAPI application, infrastructure, migrations, tests
contracts/openapi/         Generated local API contract
contracts/schemas/         Non-HTTP process protocol schemas
docs/adr/                  Accepted Phase 0 architecture decisions
.impeccable/design.json    Machine-readable snapshot of the provisional UI system
scripts/                   Development and contract utilities
tests/integration/         Cross-process smoke-test scaffold
.github/workflows/         CI quality gates and Windows smoke job
```

Future diagnostic capabilities must follow `presentation -> application -> domain`, with infrastructure implementing inward-facing ports. Windows adapters, Tool Registry, Agent, and repair actions are intentionally deferred to later phases.
