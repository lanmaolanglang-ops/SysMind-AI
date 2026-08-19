# ADR-011: Evidence-bound current-user process actions

- Status: Accepted
- Date: 2026-08-20

## Context

Phase 5 extends controlled repair beyond recoverable startup changes. A graceful GUI close can let
an application ask the user to save, while forced termination can irreversibly discard unsaved
work. PID reuse, stale windows, cross-session targets, elevated processes, critical processes, and
model- or API-supplied identifiers must not turn this feature into a general process-control API.
Service control would additionally require an administrator helper and a reviewed non-empty service
allowlist; neither is currently justified by the available evidence.

## Decision

Phase 5 permits `process.request_close_current_user@1.0` only for a single current-user,
current-session, non-elevated GUI process with a visible top-level window and direct evidence in a
completed performance diagnosis. The application generates an opaque target ID and a revision that
binds PID, creation time, user SID, session, image identity, and window ownership. Plans expire after
30 seconds. Execution revalidates the identity and sends only fixed `WM_CLOSE`; it waits at most
eight seconds and never escalates automatically.

If that close request remains pending, the user may create
`process.terminate_current_user@1.0`. It cannot be created directly from a diagnosis. It reuses no
prior consent, has a new 30-second plan, requires two explicit confirmations, warns that unsaved data
can be lost, and has no recovery claim. The adapter again validates the complete target identity,
uses only fixed `TerminateProcess`, and verifies that the bound process identity disappeared.
Restart, expiry, target drift, unreadable security state, and protected or SysMind-owned targets all
fail closed. Confirmation records and state transitions remain auditable; tickets remain
parameter-bound, short-lived, single-use, and digest-only at rest.

Process mutations are application use cases backed by a Windows adapter. They are not registered in
the model-facing Tool Registry, and neither the UI nor model can submit a PID, window handle, path,
command, message ID, or exit code.

The Phase 5 service-action allowlist is intentionally empty. No privileged helper or service mutation
module is created. A future service action requires a separate accepted ADR containing a concrete
versioned service allowlist, dependency and recovery rules, signed helper protocol, UAC behavior, and
isolated Windows validation.

## Consequences

- Graceful close preserves the application's own save/decline workflow but cannot guarantee closure.
- Forced termination is deliberately narrow, destructive, double-confirmed, and unrecoverable.
- System, security, shell, elevated, cross-user/session, background-only, and ambiguous processes are
  not candidates; protection checks fail closed.
- Completing Phase 5 does not imply that service control or a privileged helper is safe or available.
- Real state-changing verification remains restricted to Windows Sandbox or a disposable VM.
