# ADR-007: Bound and redact Windows Event Log analysis

- Status: Accepted
- Date: 2026-08-19

## Context

Phase 2 needs Application and System evidence for common Windows failures and application
crashes. Event logs are sensitive and potentially unbounded: records can contain account names,
device names, IP addresses, user-profile paths, localized text, and very large histories. A generic
command adapter would also violate the boundary that models and callers cannot execute commands.

## Decision

Define the event-log probe as an application port and implement it with the Windows Event Log API
(`wevtapi`) behind the Windows adapter. The adapter accepts only the `Application` and `System`
channels, a 1–168 hour lookback, explicit event levels, at most 32 event IDs, and a maximum of 200
returned records. It queries newest-first, polls cancellation between bounded batches, and never
accepts XPath, command, or channel strings outside the versioned DTO.

Render structured event XML locally and normalize it into a small domain record. Malformed records
are skipped. User-profile segments, account names, and IPv4 addresses are redacted; executable and
module values are reduced to filenames. Persistence stores only these normalized summaries and
rule aggregates, never raw event XML. Tool audit records contain a normalized argument hash, timing,
counts, safe errors, and no original log body.

Application and System queries fail independently. Permission denial, timeout, cancellation, and
capability absence use stable error categories. Successful evidence survives a failed channel.
Application Error and Windows Error Reporting records are aggregated locally by application,
faulting module, and exception code; general events are grouped by channel, provider, event ID, and
level. No event data is sent to a model in Phase 2.

## Consequences

- Query scope is enforceable at both the API and adapter boundaries.
- Different display languages do not control crash extraction because structured event fields and
  positional Application Error fields are used instead of localized rendered messages.
- Some providers expose incomplete or vendor-specific fields; missing values remain explicit rather
  than inferred.
- Raw-event inspection and arbitrary channels remain unavailable and require a future security and
  privacy decision.
