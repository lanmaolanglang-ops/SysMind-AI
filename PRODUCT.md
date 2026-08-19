# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Tauri 2 desktop shell with React, strict TypeScript, and Vite; a local Python FastAPI sidecar using Pydantic, SQLite, SQLAlchemy 2, and Alembic. The supported release target is Windows 10/11 x64.

## Users

Ordinary Windows users who need to understand, diagnose, and eventually optimize computer problems without learning specialist system administration tools.

## Product Purpose

SysMind AI makes local computer state understandable. It will collect narrowly scoped system evidence, correlate it locally, and present explainable diagnostic guidance. Success means a user can describe a problem in plain language and receive conclusions grounded in real, auditable evidence.

## Positioning

It is a local-first diagnostic agent rather than a generic chatbot: system access is mediated by registered, structured tools and explicit user consent instead of arbitrary model-generated commands.

## Operating Context

The product runs as a single-user Windows desktop application. The Tauri shell owns a loopback-only FastAPI sidecar. Cloud model use is optional and later phases must minimize and redact any data sent remotely.

## Capabilities and Constraints

- Phase 0 establishes only the runnable engineering foundation and backend connection states.
- The application is read-only by default and runs without administrator privileges.
- Models may never invoke Shell, PowerShell, or arbitrary commands.
- Dangerous state changes require an application-authored confirmation flow and complete audit trail.
- API keys must not be stored in plaintext in SQLite, logs, or Git.
- Actual Windows diagnostics, AI providers, Agent behavior, and system repair are outside Phase 0.

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

