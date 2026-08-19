# ADR-004: SQLite with SQLAlchemy 2 and Alembic

- Status: Accepted
- Date: 2026-08-19

## Context

SysMind AI is a local single-user application that needs durable settings and diagnostic history without a separately managed database server.

## Decision

Use SQLite through SQLAlchemy 2 and explicit Alembic migrations. Enable foreign keys on every connection and WAL journaling. Repositories will isolate persistence from application and domain layers.

Phase 0 creates only `app_metadata` plus Alembic's version table. It does not pre-create the future PRD business schema.

## Consequences

The database is portable and operationally simple. Schema changes require forward migration tests. Large future raw logs should live in managed files with database references rather than unbounded JSON rows.

