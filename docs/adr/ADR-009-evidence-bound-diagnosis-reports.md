# ADR-009: Compose diagnosis reports from deterministic, evidence-bound findings

- Status: Accepted
- Date: 2026-08-19

## Context

Phase 4 must turn ordinary-language symptoms into useful reports without allowing a model to invent
measurements or expand system access. Network checks create outbound traffic, startup and service
inventories can contain sensitive paths/accounts, and a failed collector or Provider must not erase
the evidence that did succeed.

## Decision

Classify questions locally into three application-authored templates: performance, network, and
application crash. Each template fixes its versioned tools, typed arguments, purpose, order, and
budget. Ambiguous questions use the performance template only with an explicit limitation.

Network tools are the only Phase 4 `network` risk tools. They accept two DNS names and two public IP
addresses owned by the application allowlist, at most four ICMP requests, and short timeouts. The
desktop explains this traffic before the user starts a diagnosis. The generic Agent Runtime remains
read-only-only and cannot select these tools. Startup and service tools read bounded metadata and
never enable, disable, start, or stop anything.

After tools finish, a local rule engine creates findings. Every finding contains a completed
`diagnosis_tool_call` ID and a field path; the coordinator rejects a report with a missing or failed
reference. Complete results remain local. A model, when configured server-side, receives only the
deterministic finding projection and does not receive the raw question or full tool results. Model
explanation is timeout-bounded, hashed in the audit, redacted before persistence, and optional;
failure falls back to a local explanation and adds a limitation.

Reports store structured JSON and rendered Markdown. Exports contain report material only, never
complete tool results, and apply path, IPv4, and email redaction again. Tool failure produces a
partial report when any valid evidence remains. Restarted diagnoses are marked interrupted and are
not replayed.

## Consequences

- Conclusions are traceable to local evidence and cannot be accepted solely because model prose is
  plausible.
- The rule set is deliberately conservative; “no threshold reached” means insufficient signal, not
  proof that the computer is healthy.
- ICMP can be blocked by a target or network, so packet loss is explicitly limited evidence.
- Publisher/signature metadata may be unavailable; unknown startup entries are never labelled
  malicious from absence alone.
- Repair, process termination, service changes, and privileged helpers remain Phase 5 decisions.
