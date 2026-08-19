# ADR-003: REST now, SSE for future task progress

- Status: Accepted
- Date: 2026-08-19

## Context

Phase 0 needs request/response health and lifecycle calls. Later diagnostic tasks need one-way progress events, but do not require full duplex communication.

## Decision

Use versioned JSON REST endpoints for commands and queries. Add Server-Sent Events in the later task phase for backend-to-UI progress. Do not add WebSocket infrastructure unless a future requirement demonstrates bidirectional streaming need.

All local requests carry the ephemeral session token and a correlation ID. The backend returns normalized error envelopes and validates allowed Origin values.

## Consequences

The API remains inspectable and easy to contract-test. SSE reconnect and event cursor behavior must be specified when task streaming is implemented in Phase 3.

