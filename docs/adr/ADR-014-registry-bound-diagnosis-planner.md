# ADR-014: Registry-bound and evidence-bound diagnosis planning

- Status: Accepted
- Date: 2026-08-23

## Context

The existing natural-language diagnosis coordinator classifies a question locally and executes a
fixed category template. The bounded Agent Runtime can ask for tools, but it does not produce a
persisted, explainable diagnosis plan and does not drive the ordinary diagnosis report workflow.
Phase 3.1 must add model-assisted planning without weakening the Tool Registry, network scope,
evidence, privacy, or controlled-action boundaries accepted in ADR-008 through ADR-011.

## Decision

The application owns a `DiagnosisPlanner` protocol. With no configured cloud Provider, a
deterministic Fake Planner provides offline behavior. With a configured Provider, the adapter must
return a strict structured plan containing category, confidence, status, bounded steps, exact
versioned tool names, typed arguments, and a user-visible reason for every selection.

Every proposed step is resolved against the installed Tool Registry and its Pydantic input schema
before execution. Only ordinary-user tools requiring no confirmation are eligible. Read-only
network tools remain limited to a network-category diagnosis and retain their application-owned
target allowlists. Unknown, malformed, privileged, confirmable, state-changing, destructive,
duplicate, and over-budget steps fail closed. Shell, PowerShell, command strings, arbitrary file or
registry operations, and controlled actions never enter the planner catalog.

The Context Builder sends only the redacted current question, a coarse local device/capability
summary, bounded tool descriptions, and bounded tool-result summaries. Historical summaries are
excluded by default and require an explicit future policy decision. Complete results remain local.
After the initial bounded step set completes, the planner may add one bounded revision based on
tool summaries. It may instead request missing information. It cannot execute a tool directly.

Plans, step reasons, normalized argument hashes, revisions, decisions, and their resulting tool-call
links are persisted in `agent_plans`, `diagnosis_steps`, and `agent_decisions`. Reports continue to
use deterministic findings. The Evidence Composer rejects conclusions that do not reference a
completed tool call and a real field path, and projects the call ID, exact tool, key fields, and
bounded original-result summary for audit and UI use.

## Consequences

- Ordinary diagnosis can select and revise tools without replacing the existing coordinator,
  executor, Windows adapters, report rules, or controlled-action workflow.
- A Provider protocol error or unsafe plan stops safely instead of silently substituting invented
  tools or arguments.
- The Fake Planner remains deterministic and testable offline but does not provide model-level
  semantic breadth.
- Phase 3.1 supports one bounded re-planning pass. Multi-turn user continuation, richer baseline
  retrieval, plan quality evaluation, and iterative hypothesis ranking remain Phase 3.2 work.
