# ADR-001: Use a monorepo

- Status: Accepted
- Date: 2026-08-19

## Context

The desktop shell, web UI, local Python backend, contracts, documentation, and integration tests evolve together and share a release version. Splitting them now would add contract and release coordination without independent deployment value.

## Decision

Keep all SysMind AI components in one repository. JavaScript packages use a pnpm workspace under `apps/`; Python remains an installable project under `services/backend`; cross-process contracts live under `contracts/`.

## Consequences

One change can update both sides of a contract and its tests. CI can apply focused jobs while preserving a single Phase/release boundary. The repository must still enforce component dependency direction and cannot use monorepo proximity as permission for cross-layer imports.

