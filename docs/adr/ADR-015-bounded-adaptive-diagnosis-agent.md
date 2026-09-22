# ADR-015: Bounded adaptive diagnosis continuation and hypotheses

- Status: Accepted
- Date: 2026-08-23

## Context

Phase 3.1 introduced a Registry-bound diagnosis planner, one result-driven revision, auditable tool
selection, and evidence-bound reports. A clarification request ended in `waiting_user_input`, but
there was no protocol for resuming the same diagnosis. The report also lacked explicit diagnostic
hypotheses and a machine-readable reason for stopping. Phase 3.2 must add adaptation without
weakening the existing application-owned executor and Windows adapter boundaries.

## Decision

A user answer resumes only a diagnosis currently in `waiting_user_input`. The repository records
the bounded supplemental text and changes the same diagnosis ID to `running` in one transaction.
Existing tool calls, plan revisions, evidence, and hypotheses are retained. A second concurrent or
late resume fails with a conflict instead of creating another run.

The coordinator replans from the redacted original question plus at most four bounded supplemental
answers. Every plan revision is parsed and validated again against the installed Tool Registry,
including plans returned by custom Provider adapters. Completed versioned tools are linked to the
new plan step and marked `skipped_duplicate`; they are not executed again. Running work interrupted
by backend restart remains fail-closed and is never automatically replayed, while a persisted
waiting task survives restart and may be explicitly resumed by the user.

Adaptive execution is bounded by four persisted planning rounds, eight tool calls, a 45-second
active-run timeout, and a no-new-tool duplicate fuse. Exhausting a bound records
`budget_exceeded`. Registry, privilege, confirmation, or risk violations record
`risk_limit_reached`. Other stop reasons are `evidence_sufficient`, `user_cancelled`, and
`insufficient_information`. Each transition is appended to `agent_stop_reasons`, with the latest
reason also stored on the diagnosis.

Deterministic findings produce persisted hypotheses with stable per-diagnosis IDs, rationale,
supporting and contradicting evidence references, confidence, and one of `active`, `confirmed`,
`rejected`, or `insufficient`. Absence of a threshold match is insufficient information, not
invented contradictory evidence. Supporting and contradicting references pass the same completed
tool-call and real-field-path validation as findings. Model prose remains explanatory only.

`task_user_inputs`, `diagnosis_hypotheses`, and `agent_stop_reasons`, plus bounded-agent columns on
`diagnoses`, are introduced by Alembic revision `0010_phase32`. Existing diagnosis report JSON is
read with an empty hypotheses list when the new field is absent.

## Consequences

- Clarification is a resumable state of the original task rather than a new diagnosis or chat.
- Tool calls and evidence already collected before a question remain auditable and are not repeated.
- The agent can adapt across multiple rounds but cannot loop without a fixed terminal bound.
- A backend restart never silently repeats an in-flight Windows read operation.
- No Shell, PowerShell, arbitrary command, automatic repair, registry write, or file deletion
  capability is introduced.
