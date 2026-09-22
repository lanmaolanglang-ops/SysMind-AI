# Product

<!-- impeccable:product-schema 1 -->

## Platform

Windows desktop

## Stack

Tauri 2 desktop shell with React, strict TypeScript, and Vite; a local Python FastAPI sidecar using Pydantic, SQLite, SQLAlchemy 2, and Alembic. The supported release target is Windows 10/11 x64.

## Users

Ordinary Windows users who need to understand, diagnose, and eventually optimize computer problems without learning specialist system administration tools.

## Product Purpose

SysMind AI makes local computer state understandable. It will collect narrowly scoped system evidence, correlate it locally, and present explainable diagnostic guidance. Success means a user can describe a problem in plain language and receive conclusions grounded in real, auditable evidence.

## Positioning

It is a local-first diagnostic agent rather than a generic chatbot: system access is mediated by registered, structured tools and explicit user consent instead of arbitrary model-generated commands.

## Operating Context

The product runs as a single-user Windows desktop application. The Tauri shell owns a loopback-only frozen FastAPI sidecar. Phase 6 distributes a per-user signed NSIS installer and signature-verified updates while preserving local diagnostic data; Phase 5 actions remain evidence-bound and the optional model remains outside the action path.

## Capabilities and Constraints

- Phase 4 maps performance, network, and application-crash questions to bounded plans and produces reports whose conclusions reference real tool calls and field paths.
- The application is read-only by default and runs without administrator privileges.
- Models may never invoke Shell, PowerShell, or arbitrary commands.
- Dangerous state changes require an application-authored confirmation flow and complete audit trail.
- API keys must not be stored in plaintext in SQLite, logs, or Git.
- Full tool results stay local while only bounded summaries may enter model context. Unknown tools, invalid arguments, repeated calls, and exceeded budgets fail closed.
- Network checks generate limited outbound traffic only to fixed application-owned test targets after the user starts a network diagnosis.
- Phase 5 supports current-user startup disable/restore, bounded GUI close, and double-confirmed forced termination only after a close remains pending. Service, network, privileged, bulk, and generic repair actions remain unavailable.

## Brand Commitments

The confirmed product name is “SysMind AI”. Product language should be calm, direct, and understandable to non-technical users without hiding uncertainty or risk.

## Evidence on Hand

The product and architecture baseline is `docs/SysMind-AI-PRD-and-Architecture.md`. No logo, commercial claims, customer evidence, or production telemetry exists yet and none should be fabricated.

## Product Principles

- Local first and minimum necessary data.
- Read-only and least privilege by default.
- Evidence before explanation.
- Explicit consent before any future state change.
- Every important action remains traceable.

## Accessibility & Inclusion

The desktop interface must expose connection, loading, failure, and recovery states without relying on color alone, support keyboard focus, and use plain-language error recovery.
