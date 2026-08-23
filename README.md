# SysMind AI

SysMind AI is a local-first Windows diagnostic assistant for ordinary users. The current Release Candidate turns a plain-language symptom into a bounded plan, real local evidence, an uncertainty-aware report, and safe next steps. Every important conclusion exposes its evidence source, observation time, and key metric while technical identifiers stay behind disclosure. The application does **not** execute model-authored commands, manage services, elevate privileges, or expose generic system changes.

RC2 has also been exercised as an unsigned Local Validation Build on one Windows 11 x64 device,
including real diagnosis tools, fresh-data startup, bundled-backend lifecycle, silent install, and
data-preserving uninstall. This is single-device evidence, not a signed production-release claim.

The product and architecture baseline is [docs/SysMind-AI-PRD-and-Architecture.md](docs/SysMind-AI-PRD-and-Architecture.md).

## Get the preview

v0.1.0-preview targets Windows 10/11 x64. Download the installer and its checksum from the
[GitHub Releases page](https://github.com/lanmaolanglang-ops/SysMind-AI/releases), verify the SHA-256
value, and run the per-user installer. No separate Python or Node.js installation is required for
the packaged application.

The current Local Validation Build is unsigned. Windows may identify its publisher as unknown; use
it only when you trust the repository and have verified the published checksum. It is a preview, not
a production-signed release. See [INSTALL.md](INSTALL.md) for installation and uninstall behavior,
[USER_GUIDE.md](USER_GUIDE.md) for the diagnosis flow, and [LIMITATIONS.md](LIMITATIONS.md) before
using the preview.

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
                                                    ▲
                                                    │ inward-facing ports
                                          Bounded Windows adapters
```

The Tauri process owns the exact child process it creates. On Windows, the child is assigned to a Job Object with `KILL_ON_JOB_CLOSE`; normal exit first requests graceful backend shutdown and only terminates that owned child after a timeout. A development launcher uses Python today and the same abstraction accepts a frozen executable later.

## Current v0.1.0-preview capabilities

- Start, monitor, cancel, and revisit a local quick scan.
- Collect normalized OS, CPU, GPU, memory, fixed-volume, process snapshot, and high-usage process evidence.
- Compare the latest completed scans with a bounded ten-scan CPU, memory, and disk-usage baseline.
- Preview and confirm deletion of terminal read-only history, with configurable retention and cleanup audit.
- Preserve partial results when a collector is unavailable or times out.
- Persist scan summaries and per-step audit events with collector name, version, timing, and safe error mapping.
- Run fixture-based tests on every platform and real read-only Windows adapter/API smoke tests on Windows.
- Query only the `Application` and `System` event channels with a 1–168 hour window, selected levels, optional event IDs, and a hard 200-record maximum.
- Normalize and redact event evidence locally, tolerate malformed records, and preserve one channel when another is denied or unavailable.
- Aggregate common provider/event-ID failures plus Application Error and Windows Error Reporting crashes without storing raw event XML.
- Start, monitor, cancel, and revisit log analyses through the local API and desktop UI.
- Run a persisted Agent task against an exact user-selected allowlist of versioned, read-only tools.
- Stream ordered task events over reconnectable SSE and recover interrupted tasks as failed without replaying model or tool calls.
- Enforce total time, reasoning-round, tool-call, repeated-call, per-tool concurrency, and global task-concurrency budgets.
- Use a deterministic offline Fake Provider by default, with a tested OpenAI-compatible Chat Completions adapter available for server-side composition.
- Keep complete tool results and call audit data local; only bounded tool summaries enter subsequent model context.
- Build persisted, structured diagnosis plans from the user question and the installed Tool Registry;
  every selected tool has a reason and validated typed arguments.
- Re-plan adaptively within four rounds and eight tool calls, or ask for missing symptom information;
  user answers resume the same persisted diagnosis while the deterministic Fake Planner remains offline-capable.
- Persist evidence-backed diagnostic hypotheses and explicit stop reasons, and skip completed tools
  if a resumed plan selects them again.
- Treat capability observations separately from diagnostic conclusions, reduce confidence when tool
  coverage is incomplete, and state plainly when current evidence cannot determine a cause.
- Preserve partial evidence reports when a tool fails or a bounded planning budget is reached.
- Inspect current-user/WinHTTP proxy metadata, fixed allowlisted DNS and ICMP targets, startup sources, scheduled-task names, and Windows service metadata.
- Generate deterministic local findings before optional model explanation; every finding references a completed tool call and field path.
- Project every conclusion to its tool-call ID, exact tool version, key fields, and bounded original
  result summary; unsupported evidence references fail closed.
- Present evidence source, observation time, and key metrics in plain language before technical
  tool-call IDs and field paths, including redacted Markdown and JSON exports.
- Preserve partial reports when tools or the model fail, and explicitly list ambiguity, unavailable evidence, and other limitations.
- Revisit report history, submit helpful/not-helpful feedback, and export redacted JSON or Markdown.
- Generate a diagnosis-bound plan for one current-user startup item, record an explicit per-item decision, revalidate the target, verify the result, and offer conflict-safe recovery.
- Freeze the backend with its Alembic migrations, embed it as a private Tauri resource, and refuse a release-time fallback to system Python.
- Build a current-user NSIS installer, preserve local data across upgrades and silent uninstall, and offer explicit deletion during interactive uninstall.
- Enforce one desktop instance and provide user-visible, signature-verified update checks with explicit install/restart.
- Require Windows Authenticode and Tauri update-signing inputs for formal release builds while keeping every credential outside the repository.

## Safety boundary

- The backend host is a validated literal `127.0.0.1`; `0.0.0.0` is rejected.
- Every API request requires an ephemeral `X-SysMind-Session` token.
- Browser/Tauri origins are allowlisted and correlation IDs cross the API boundary.
- Provider credentials are submitted only through the authenticated local settings flow, held briefly
  in form/request memory, and stored by the backend in Windows Credential Manager. They are never
  persisted in SQLite, browser storage, reports, or logs. `FakeSecretService` remains memory-only.
- Logs are structured JSON and redact common secret fields.
- Collectors are application-owned, versioned, timeout-bounded, and read-only.
- GPU detection uses one fixed application-authored CIM query; no user or model input reaches PowerShell.
- The Windows GPU adapter reports metadata only and explicitly marks real-time utilization and
  used-memory telemetry unavailable instead of estimating either value.
- History deletion is revision-bound. Active work and diagnoses linked to controlled-action audit
  are protected; retention never deletes actions, confirmations, action events, or recovery records.
- Event Log collection uses the Windows Event Log API directly; callers cannot provide XPath, arbitrary channels, or commands.
- Event summaries redact user-profile names, account identifiers, and IPv4 addresses before persistence. Raw event XML is not stored.
- The Tool Registry is an exact allowlist; unknown tools, invalid arguments, state-changing risk levels, confirmation-requiring tools, and privilege-requiring tools are rejected.
- Agent prompts treat goals and tool evidence as untrusted data. State-changing startup actions use a separate application-authored executor and cannot be selected by a model.
- Confirmation tickets are single-use, expire within two minutes, and bind the action, target revision, parameters, and sidecar session; only their digest is audited.
- Network tools use fixed application allowlists (`one.one.one.one`, `www.microsoft.com`, `1.1.1.1`, and `8.8.8.8`) plus hard count and timeout bounds. Starting a network diagnosis is the explicit user action that authorizes this limited traffic.
- A configured remote Provider may receive the redacted current question, a minimal device summary,
  eligible read-only tool descriptions, and bounded redacted observation/finding summaries. Complete
  tool results, raw event XML, credentials, user files, and system-modification capabilities remain
  local; provider failures fall back to local rules.

## Development requirements

### Optional OpenAI-compatible Provider

The desktop settings panel accepts an HTTPS endpoint, model, and API key. On Windows, the backend
stores the key in Credential Manager and persists only non-sensitive settings in SQLite. Loopback
HTTP endpoints are accepted for local development; remote plaintext HTTP endpoints are rejected.
Leaving the Provider unconfigured keeps the application in the local-rules/Fake Provider fallback.

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
& services/backend/.venv/Scripts/python.exe -m pip install -e "services/backend[dev,packaging]"
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

Run only the real Windows read-only smoke tests:

```powershell
& services/backend/.venv/Scripts/pytest.exe services/backend/tests/test_windows_diagnostics.py -m windows_smoke -vv
& services/backend/.venv/Scripts/pytest.exe services/backend/tests/test_event_logs.py -m windows_smoke -vv
```

Phase 5A state-changing verification is excluded from the commands above. Run it only inside a
disposable Windows Sandbox/VM that satisfies the dual safety gate documented in
`tests/integration/README.md`:

```powershell
.\scripts\run-phase5a-isolated-tests.ps1 -ConfirmIsolatedEnvironment
```

## Build a Windows installer

An unsigned package is for local validation only:

```powershell
.\scripts\package.ps1 -Version 0.1.0
```

The script runs quality gates, freezes and smoke-tests the backend without relying on system Python,
then creates the NSIS installer. A formal release additionally requires protected Windows certificate
and Tauri updater signing inputs and is run by `.github/workflows/release.yml`; the script fails when
any required input is missing. Never put certificate material or private updater keys in the repo.

Disposable Windows install/uninstall checks are gated in the same way as Phase 5 mutation tests:

```powershell
.\scripts\run-phase6-isolated-tests.ps1 `
  -InstallerPath '<path-to-setup.exe>' `
  -ConfirmIsolatedEnvironment
```

See [the installation guide](INSTALL.md), [user guide](USER_GUIDE.md),
[current limitations](LIMITATIONS.md), [release checklist](docs/release-checklist.md),
[privacy notice](docs/privacy.md),
[security policy](.github/SECURITY.md), [security model](docs/security.md),
[v0.1.0 release notes](docs/releases/v0.1.0.md), and
[third-party license notes](docs/third-party-licenses.md).

The minimal RC1 product-validation scenarios are recorded under
[docs/cases/](docs/cases/README.md).
The current-device RC2 record is
[docs/progress/release-candidate-2-local-validation-complete.md](docs/progress/release-candidate-2-local-validation-complete.md).

## License

SysMind AI is licensed under the [MIT License](LICENSE). Third-party components retain their own
licenses and required notices.

## Directory guide

```text
apps/desktop/              React/Vite UI and Tauri 2 shell
services/backend/          FastAPI application, infrastructure, migrations, tests
contracts/openapi/         Generated local API contract
contracts/schemas/         Non-HTTP process protocol schemas
docs/adr/                  Accepted architecture decisions
INSTALL.md                 Preview installation and uninstall instructions
USER_GUIDE.md              Ordinary-user diagnosis walkthrough
LIMITATIONS.md             Supported scope and known limitations
.impeccable/design.json    Machine-readable snapshot of the provisional UI system
scripts/                   Development and contract utilities
tests/integration/         Cross-process smoke-test scaffold
.github/workflows/         CI quality gates and Windows smoke job
```

The implemented dependency direction is `presentation -> application -> domain`; SQLAlchemy repositories, model providers, and Windows adapters implement inward-facing ports. Service control, privileged helpers, bulk or automatic repair, and unrestricted model-selected tools remain unavailable. Phase 5 process actions stay outside the model Tool Registry and require per-action evidence and consent.
