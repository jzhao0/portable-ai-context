# AGENTS.md

## Mission

Build a cross-platform, source-agnostic conversation migration engine. The project is not a transcript exporter; it should preserve continuation-critical context while keeping extraction auditable and privacy-aware.

## Architectural rules

1. Source-specific parsing belongs in `src/portable_ai_context/adapters/`.
2. Compiler code must depend only on the canonical `Conversation` model, not on ChatGPT internals.
3. Runtime/session/account metadata must never be required for canonicalization.
4. Prefer allowlists over parse-everything-then-redact.
5. Secret scanners may report categories/counts but must not print matched secret values.
6. Never add private raw user exports to fixtures or tests.
7. Local extraction/verification/bundling must not require an AI API.
8. New adapters need synthetic or explicitly public conformance fixtures.
9. Keep mandatory dependencies minimal; standard library is preferred in core.
10. Any schema or bundle format before v1.0 must be labeled unstable.

## Verification before commit

Run:

```bash
python -m compileall -q src tests
PYTHONPATH=src python -m unittest discover -s tests -v
```

For packaging changes also build a wheel and install it into a clean environment.
