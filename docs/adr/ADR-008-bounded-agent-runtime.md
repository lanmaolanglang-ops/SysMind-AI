# ADR-008: Bound and audit the Phase 3 Agent runtime

- Status: Accepted
- Date: 2026-08-19

## Context

Phase 3 introduces model-directed orchestration over evidence collectors. Model output and user goals
are untrusted, providers may fail or disconnect, and an unbounded reasoning loop could consume local
or remote resources. Complete system evidence may also be too sensitive to place in later prompts.

## Decision

The application owns a versioned Tool Registry. A task stores an exact allowlist chosen from that
registry. Policy permits only read-only, user-privilege tools that do not require confirmation;
unknown names or versions, invalid structured arguments, and every other risk class fail closed.
There is no generic command, Shell, PowerShell, process-control, repair, or network tool.

The Agent Brain accepts only typed provider actions and enforces total time, reasoning-round,
tool-call, repeated-call, parallel-call, per-tool concurrency, and global task-concurrency limits.
User goals and tool observations are marked as untrusted data in the model context. Full tool results
and structured call records remain in local SQLite; subsequent model turns receive only a
tool-specific bounded summary. Audit rows record hashes, timing, status, stable errors, and redacted
arguments. Rejected arguments for unregistered tools are never persisted verbatim.

Tasks emit ordered persisted events. The loopback API exposes those events as SSE with event IDs,
heartbeats, `Last-Event-ID`, and an explicit cursor so a desktop reconnect can resume without gaps.
Cancellation propagates through the manager, provider wait, and tool executor. A process restart
marks interrupted tasks failed and never replays an uncertain model or tool call.

Production composition uses the deterministic Fake Provider by default so the feature is testable
offline and visibly labelled as such. The OpenAI-compatible adapter is a separate infrastructure
implementation. Its credential is supplied only to server-side memory, HTTPS is required except for
loopback development, and secrets are not accepted by the local HTTP API, stored, or logged.

## Consequences

- Model behavior cannot expand the installed tool surface or bypass typed validation and policy.
- A task terminates predictably under repetition, overload, timeout, cancellation, provider failure,
  malformed response, or restart.
- SSE delivery is reconnectable but remains a local task-event channel, not a remote provider stream.
- Enabling a real provider requires a later secure settings/secret-injection composition decision;
  the Phase 3 desktop intentionally exposes no API-key or provider-endpoint fields.
- State-changing tools and generated diagnostic reports remain later-phase decisions.
