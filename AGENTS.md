# SysMind AI Engineering Instructions

Before changing the project, read `docs/SysMind-AI-PRD-and-Architecture.md` and the applicable ADRs.

## Architecture boundaries

- Preserve the dependency direction `presentation -> application -> domain`.
- Infrastructure implements interfaces required by application or domain code.
- Windows-specific integrations belong behind Windows adapters in later phases.
- An AI model must never call Windows APIs, Shell, PowerShell, or arbitrary commands directly.
- Future model actions are limited to versioned tools in the Tool Registry.

## Safety boundaries

- Default to loopback-only, read-only, least-privilege behavior.
- Never store API keys or session tokens in SQLite, logs, source control, or frontend browser storage.
- Never log Authorization headers or full sensitive request data.
- Any future system-changing action requires explicit, parameter-bound user confirmation and audit logging.

## Quality gates

- Keep Phase work inside its documented scope.
- Add tests for behavior and failure modes, not only happy paths.
- Run backend lint, typecheck, and pytest plus frontend lint, typecheck, and tests before handoff.
- Do not create placeholder modules for future phases.

