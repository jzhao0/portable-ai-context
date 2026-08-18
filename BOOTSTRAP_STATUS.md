# Bootstrap Status — 2026-08-18

## Working project name

`portable-ai-context` / **Portable AI Context**

This is a working title. Rename before the first public tagged release if a better conflict-free brand is selected.

## Verified locally

- 6 unit tests pass.
- `python -m portable_ai_context --help` works from source.
- wheel build succeeds: `portable_ai_context-0.1.0a1-py3-none-any.whl`.
- wheel installs into a clean virtual environment without network access.
- installed `paic` CLI starts successfully.
- real PoC clean HTML re-import: 425 canonical messages.
- real PoC raw ChatGPT HTML re-import: 425 canonical messages.
- `.aicb` bundle built from the real clean archive retains 425 messages.
- raw-page privacy inspection detects runtime marker categories without exposing their values.

## Public repository boundary

Do not commit:

- the real 8 MB ChatGPT HTML fixture;
- the real 425-message clean archive;
- API keys or Keychain-specific user configuration;
- generated migration prompts containing private project history.

## Repository milestone

The public GitHub repository is initialized under `jzhao0/portable-ai-context` with the modular alpha codebase, documentation, tests, schema, and cross-platform CI configuration.

## Next milestone

1. Confirm the GitHub Actions Linux/macOS/Windows matrix passes on the bootstrap commit.
2. Open scoped issues for ChatGPT shared-URL hardening, Claude adapter, Gemini adapter, exact token budgets, and browser capture.
3. Add package/release CI and synthetic golden fixtures.
4. Keep the working project name provisional until the first tagged public release.
