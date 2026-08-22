# ADR-013: Windows Credential Manager for provider credentials

- Status: Accepted
- Date: 2026-08-22

## Context

ADR-005 leaves the production Windows secret adapter choice open. Provider configuration now
needs persistent non-sensitive settings while API keys must stay out of SQLite, logs, reports,
frontend storage, and ordinary read responses.

## Decision

Store OpenAI-compatible provider API keys as current-user Generic Credentials in Windows
Credential Manager under a fixed, application-owned target name. SQLite stores only provider,
model, HTTPS-or-loopback endpoint, and the opaque fixed secret reference. Settings reads expose
only whether a credential exists. A submitted key is held only for the request and cleared from
the desktop form after completion.

Connection tests use the server-side credential, a five-second bound, stable error categories,
and append-only audit metadata without request/response bodies or authorization data. Runtime
composition selects the real provider only when settings and the credential are both valid;
otherwise it explicitly retains the local deterministic fallback.

## Consequences

- Provider credentials follow the signed-in Windows user and are not portable with the database.
- Non-Windows development and tests use the in-memory fake secret service only when explicitly
  injected; production composition fails closed rather than persisting a substitute secret.
- Applying changed provider settings to already-running coordinators requires a backend restart.
