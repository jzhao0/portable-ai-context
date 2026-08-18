# Contributing

Contributions are welcome, especially new source adapters and synthetic fixtures.

## Rules for adapters

An adapter must:

1. return canonical `Conversation` objects;
2. document exactly which source fields are emitted;
3. exclude account/session/auth/runtime metadata by default;
4. include tests that use synthetic or explicitly public fixtures;
5. never add real user conversation exports to the repository.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

Keep the core dependency-light. New mandatory runtime dependencies require a concrete portability or security benefit.
