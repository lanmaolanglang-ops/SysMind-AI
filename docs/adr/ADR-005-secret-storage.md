# ADR-005: Secrets stay outside ordinary persistence

- Status: Accepted
- Date: 2026-08-19

## Context

Future model provider credentials must survive application restarts without entering SQLite, logs, source control, frontend storage, or exported reports.

## Decision

Application code depends on a `SecretService` port. Phase 0 supplies only `FakeSecretService`, an in-memory implementation for tests and development. The production Windows adapter will use Windows Credential Manager or a narrowly scoped DPAPI implementation after a focused security review.

Database records may later contain an opaque secret reference, never the credential value. Logging sanitizes common secret field names, but callers remain responsible for not placing secrets in messages.

## Consequences

Secret storage can change without affecting application use cases. Provider configuration is intentionally deferred until the Windows secure-storage adapter exists. The final Credential Manager versus DPAPI choice remains an implementation decision inside this accepted boundary.

