# ADR-006: Bounded read-only Windows collectors

- Status: Accepted
- Date: 2026-08-19

## Context

Phase 1 needs trustworthy Windows evidence before any Agent exists. Collection must remain compatible with the architecture baseline, expose partial failure, and never create a generic shell path that a future model could reach.

## Decision

Define collector protocols in the application layer and normalized immutable records in the domain layer. Implement those protocols in a Windows adapter using `psutil`, `platform`, the Windows registry, and one fixed application-authored CIM query for GPU metadata.

Expose the collectors through versioned, read-only tool specifications with explicit timeouts. A quick-scan coordinator owns execution, cancellation, error mapping, progress, and persistence. It records a summary plus a per-step audit event. A failed or unavailable collector produces a partial scan and does not discard successful evidence.

Process CPU percentages are normalized to whole-machine utilization. “System Idle Process” is excluded from high-usage findings. Phase 1 provides no terminate, service-control, configuration, registry-write, arbitrary command, Agent, or model entry point.

## Consequences

- Domain and application code remain testable with deterministic fixture probes.
- Windows-specific details cannot leak into presentation or Agent layers.
- GPU availability depends on Windows PowerShell/CIM and may legitimately yield a partial result.
- `asyncio.to_thread` timeouts stop awaiting a collector but cannot forcibly terminate a Python thread; adapters therefore use their own bounded operations, and the Tauri owner still enforces sidecar shutdown.
- Adding future collectors requires a versioned specification, normalized output, safe error mapping, and audit coverage.
