# SysMind AI privacy notice

Last updated: 2026-08-22

SysMind AI is local-first Windows diagnostic software. System evidence, reports, task history,
confirmation records, and recovery material are stored on the current computer unless the user
explicitly exports a report or enables a remote model provider.

## Optional model data flow

Without a configured Provider, scans and diagnosis reports remain local and use deterministic rules.
When a Provider is configured, it receives only the bounded deterministic finding projection:
category, code, severity, title, explanation, confidence, and evidence identifiers/field paths. The
raw user question and complete tool results are not sent. Provider prose is labelled auxiliary and
cannot create findings, evidence, confirmations, or action controls.

## Data stored locally

- SQLite stores scans, bounded event summaries, diagnostic reports, task and tool audit records,
  feedback, and controlled-action state.
- Rotating application logs contain structured, redacted operational events. Authorization headers,
  session tokens, provider keys, and complete sensitive requests are excluded.
- Startup-item recovery material is stored in the application's private local-data directory so a
  user-confirmed restore can be attempted safely.
- The Tauri installation uses `%LOCALAPPDATA%\\ai.sysmind.desktop`. Interactive uninstall asks
  separately before deleting that directory; upgrades and silent uninstall preserve it.

The user can export redacted JSON or Markdown reports. Export is an explicit action and the selected
destination is outside SysMind AI's retention control.

## Network activity

- The desktop communicates with its backend only over a random `127.0.0.1` port protected by a
  per-launch session token.
- A user-started network diagnosis may contact only the fixed targets disclosed in the interface.
- Checking for an application update contacts the configured HTTPS release endpoint. The release
  host can observe normal connection metadata such as IP address and user agent; diagnostic content
  is not included.
- The default Fake Provider is offline. If a remote model provider is enabled in a future supported
  configuration, only the bounded, redacted evidence projection documented by the application is
  sent. Raw event XML and complete tool results remain local.

## Credentials

Session tokens exist only in process memory and child-process environment. Provider API keys use the
current-user Windows Credential Manager adapter and are never stored in SQLite, browser storage,
logs, exports, or source control.

## Retention and deletion

Terminal scan, diagnosis, and log-analysis history is retained locally for 30 days by default. The
user can select 7–3650 days and run cleanup immediately. Cleanup does not remove controlled-action,
confirmation, action-event, or recovery audit records. Individual deletion first displays the number
of dependent detail records and requires the exact preview revision. Before deleting local data,
export any reports that must be kept.

SysMind AI includes no mandatory product analytics or crash telemetry in Phase 6. A future telemetry
feature requires a separate opt-in design and privacy update.
