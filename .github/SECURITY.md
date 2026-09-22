# Security policy

## Supported versions

SysMind AI has not yet published a production-signed binary release. Security fixes currently target
the latest `main` branch. After v0.1.0 is published, the latest supported release line will receive
security fixes; older development artifacts are unsupported.

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/lanmaolanglang-ops/SysMind-AI/security/advisories/new).
Do not open a public issue for a suspected vulnerability.

Include the affected version or commit, impact, reproduction steps, and any suggested mitigation.
Do not include real API keys, session tokens, personal diagnostic exports, or unredacted logs. Use
synthetic evidence whenever possible.

The maintainers will coordinate disclosure through the private advisory. Please do not publish the
report before a fix and disclosure plan have been agreed.

## Security boundary

The supported trust and release-integrity boundaries are documented in
[`docs/security.md`](../docs/security.md). Unsigned local installers are development artifacts and
must not be represented as production releases.
