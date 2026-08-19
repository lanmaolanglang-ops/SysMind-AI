# ADR-010: Parameter-bound current-user startup actions

- Status: Accepted
- Date: 2026-08-20

## Context

Phase 5 introduces the first state-changing capability. A model suggestion, loopback request,
replayed confirmation, stale startup inventory, or replaced Startup-folder file must not cause an
operation on a different target. Process termination and service control are less recoverable or
require a privileged helper and are outside the approved first increment.

## Decision

Phase 5A permits exactly `startup.disable_current_user@1.0` and
`startup.restore_current_user@1.0`. Targets are restricted to a single current-user Run value or a
single ordinary file directly inside the current-user Startup folder. The API accepts only opaque
application-issued item IDs and observed revision hashes; registry paths and filesystem paths are
resolved inside the Windows adapter. Machine-wide entries, scheduled tasks, links, reparse points,
UNC/device paths, directories, arbitrary registry/file operations, processes, services, networking,
and elevation are rejected.

State-changing execution is isolated from the model-facing Agent Tool Executor. An action must be
derived from a completed diagnosis containing startup evidence. The desktop displays the exact
target and effect, then records a per-action decision. Confirmation creates an authenticated,
single-use ticket bound to action, tool, target hash, observed revision, sidecar session, nonce, and
a maximum two-minute lifetime. Only the ticket digest is persisted. Execution consumes the ticket
atomically, re-reads target identity, creates local recovery material, changes one item, and verifies
the result with a fresh read. Restarted actions are marked interrupted and never replayed.

Recovery is a new action with a new confirmation. It refuses to overwrite a slot changed or occupied
after disable. Registry value data and isolated files stay in the local recovery directory; SQLite
stores references, hashes, decisions, state transitions, errors, and verification outcome.

## Consequences

- Phase 5A remains ordinary-user and adds no privileged helper or UAC surface.
- A stale plan, altered target, expired/tampered/replayed ticket, or recovery conflict fails closed.
- Disabling a startup item can affect expected login behavior, but it does not uninstall or delete
  the application and offers recovery while the target slot remains safe.
- Process termination and service state changes require a separate Phase 5B review and approval.
