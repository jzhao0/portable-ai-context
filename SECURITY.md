# Security Policy

## Scope

Portable AI Context processes potentially sensitive conversation history. Treat source files and generated bundles as private unless you intentionally share them.

## Security principles

- Runtime/session/account metadata should never be required for migration.
- Adapters should use allowlists rather than "parse everything then redact".
- Secret scanners must not print secret values.
- API keys must be supplied via environment/secret stores, never persisted in bundles.
- A conversation-body secret is different from webpage runtime metadata; the tool warns but does not silently rewrite user content by default.

## Reporting

Please open a private security advisory on GitHub when available. Do not include real credentials, tokens, cookies, or private conversation content in public issues.
