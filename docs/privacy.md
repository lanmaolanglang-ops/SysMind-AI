# SysMind AI privacy notice

Last updated: 2026-08-22

SysMind AI is local-first Windows diagnostic software. System evidence, reports, task history,
confirmation records, and recovery material are stored on the current computer unless the user
explicitly exports a report or enables a remote model provider.

## Optional model data flow

Without a configured Provider, scans and diagnosis reports remain local and use deterministic rules.
When a Provider is configured, diagnosis planning may send the redacted current question, a minimal
device/capability summary, bounded descriptions of eligible read-only tools, and bounded redacted
observation summaries from completed tools. Report explanation may send the deterministic finding
projection: category, code, severity, title, explanation, confidence, and evidence identifiers/field
paths. Provider prose is labelled auxiliary and cannot create findings, evidence, confirmations, or
action controls.

SysMind AI does not send complete tool results, raw event logs or event XML, credentials, user file
contents, confirmation tickets, or system-modification capabilities to a Provider. Redaction reduces
exposure but cannot guarantee that every user-entered sentence is anonymous; do not enter secrets or
unnecessary personal information in a diagnosis question.

## Data stored locally

- SQLite stores scans, bounded event summaries, diagnostic reports, task and tool audit records,
  feedback, and controlled-action state.
- Rotating application logs contain structured, redacted operational events. Authorization headers,
  session tokens, provider keys, and complete sensitive requests are excluded.
- Startup-item recovery material is stored in the application's private local-data directory so a
  user-confirmed restore can be attempted safely.
- The Tauri installation uses `%LOCALAPPDATA%\ai.sysmind.desktop`. Interactive uninstall asks
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
- The default deterministic Provider is offline. If a remote model provider is enabled, only the
  bounded planning and explanation context described above is sent. Raw event XML and complete tool
  results remain local.

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
