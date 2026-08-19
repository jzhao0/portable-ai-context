# Portable AI Context

> **Working title / alpha.** Turn long AI conversations into privacy-aware, verifiable context packages another model can actually continue from.

**Export is not migration. Preserve the state, not the transcript.**

Portable AI Context (`paic`) is a local-first Python toolkit for extracting conversations from supported sources, normalizing them into a canonical schema, auditing privacy and completeness, exporting portable artifacts, and compiling long histories into migration prompts.

## Why

Long-running AI conversations accumulate decisions, corrections, commands, experiment results, preferences, and project state. Copying the raw transcript into a new model is often wasteful or impossible. Traditional exporters solve *serialization*; this project targets *handoff quality*.

The design goals are:

- **Portable:** source adapters normalize different conversation formats.
- **Privacy-aware:** runtime/session metadata is excluded by whitelist; body-secret detection warns without printing secret values.
- **Verifiable:** counts, message hashes, conversation digest, snapshot metadata, and tail hashes make truncation visible.
- **Local-first:** extraction, normalization, inspection, conformance checking, deterministic checkpoint generation, and bundle creation need no AI API.
- **Compiler-agnostic:** migration compilation uses an OpenAI-compatible backend today and is designed for more providers later.
- **Cross-platform:** the core and CLI are Python 3.10+ and avoid OS-specific dependencies.

## v0.1 alpha scope

### Inputs

- Migrator Clean HTML
- compact TXT (`<<<USER>>>` / `<<<ASSISTANT>>>`)
- JSONL (`role`, `text`)
- saved ChatGPT share-page HTML / safe archive HTML
- ChatGPT shared URL (**experimental**; browser fallback is best-effort)
- single-conversation Claude JSON export subset (local `.json`; see [`docs/claude-adapter.md`](docs/claude-adapter.md))
- Gemini Apps Google My Activity JSON subset (local `.json`; see [`docs/gemini-adapter.md`](docs/gemini-adapter.md))
- browser-capture JSONL produced by the experimental Chromium extension in [`extension/`](extension/)

### Outputs

- clean HTML
- compact TXT
- clean JSONL
- `.aicb` portable bundle
- integrity report
- privacy report
- content-free adapter conformance report
- deterministic no-AI extractive checkpoint + reproducibility report
- optional migration prompt via OpenAI-compatible API
- compile budget report with token estimates / exact injected counts when configured

### Not yet promised

- Grok adapter
- automatic multi-conversation Claude archive selection
- Claude shared-page HTML adapter
- reconstruction of original Gemini chat-thread boundaries from flat My Activity exports
- localized Gemini activity prompt formats beyond the documented alpha subset
- bundled model-specific exact tokenizer packages (exact counters can be injected through the compiler API)
- Firefox browser-capture support or signed browser-store distribution
- desktop GUI
- stable `.aicb` schema
- MCP handoff server

Those belong on the roadmap, not in the v0.1 contract.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .
```

Confirm the installed CLI version:

```bash
paic --version
```

Inspect a conversation:

```bash
paic inspect conversation.clean.html
```

Run the shared content-free adapter/canonical round-trip contract:

```bash
paic conform conversation.clean.html
```

`paic conform` reports source kind, message count, integrity digest, named structural checks, and generic violation codes without printing the conversation title, message/tail text, or source path. See [`docs/adapter-conformance.md`](docs/adapter-conformance.md).

Create a deterministic local checkpoint with no AI/API call:

```bash
paic checkpoint conversation.clean.html -o checkpoint
```

This produces `CHECKPOINT.md` plus a content-free `checkpoint-report.json`. The default policy is deterministic and extractive: it prioritizes latest user/assistant evidence, the first-user goal anchor, recent tail messages, and explicit state-marker messages. It does **not** semantically decide which statements are true/current/completed. See [`docs/deterministic-checkpoint.md`](docs/deterministic-checkpoint.md).

Extract normalized artifacts:

```bash
paic extract conversation.clean.html -o out
```

Create a portable bundle:

```bash
paic bundle conversation.clean.html -o project.aicb
```

Verify integrity and tail metadata:

```bash
paic verify conversation.clean.html
```

Compile a semantic migration prompt using an OpenAI-compatible API:

```bash
export PAIC_API_KEY='...'
paic compile conversation.clean.html \\
  --api-base https://api.example.com/v1 \\
  --map-model fast-model \\
  --final-model strong-model \\
  --profile standard \\
  -o migration
```

Named checkpoint/compiler budgets are `lite` (4,000), `standard` (16,000), and `full` (64,000) tokens. You can instead use `--budget <tokens>`. The dependency-free CLI uses an explicit character/token estimate; exact tokenizer counters can be injected through the Python APIs. See [`docs/token-budgets.md`](docs/token-budgets.md) and [`docs/deterministic-checkpoint.md`](docs/deterministic-checkpoint.md).

For pages where direct capture is unreliable, the experimental Chromium browser extension uses only `activeTab` + `scripting`, previews message count and tail text before download, and exports canonical JSONL locally. See [`extension/README.md`](extension/README.md) and the [`browser-extension threat model`](docs/browser-extension-threat-model.md).

`paic` never requires API access for extraction, inspection, conformance checking, deterministic checkpoint generation, verification, or bundle creation. Only AI-assisted `paic compile` requires a model backend.

## Verification status

The project distinguishes real live validation from synthetic/conformance coverage. ChatGPT shared-URL capture has real macOS, Windows, and Linux smoke evidence, and the browser extension has a real Windows Edge smoke. Claude and Gemini adapters currently have synthetic fixtures plus cross-platform CI; deliberately non-sensitive real-export validation remains tracked in Issue #17.

The shared adapter conformance contract adds one common post-canonicalization gate for current and future adapters. It verifies canonical roles/indices/text, integrity consistency, and clean HTML / compact TXT / JSONL digest-preserving round trips, but it does **not** replace real provider-source validation.

The deterministic checkpoint mode is a reproducible extractive fallback, not a semantic summary. Its derived artifact pattern-redacts the secret-like formats currently recognized by PAIC while leaving canonical history unchanged; it is not a general confidentiality scrubber and should be reviewed before sharing.

See [`docs/release-readiness-0.1.0a2.md`](docs/release-readiness-0.1.0a2.md) for the full evidence ledger and known alpha limitations.

## Canonical model

Every adapter produces a `Conversation` with:

- source metadata
- snapshot metadata when available
- ordered messages
- canonical roles
- per-message metadata

The initial bundle schema is documented in [`schemas/conversation-bundle.schema.json`](schemas/conversation-bundle.schema.json). It is explicitly **alpha** and may change before 1.0.

## Privacy model

Two different classes of secrets are treated differently:

1. **Page/runtime secrets** — account/session/auth/bootstrap data that is not part of the conversation. Adapters use whitelists and do not emit it.
2. **Secrets typed into the conversation body** — these are user content. Canonical history is not silently rewritten. Privacy inspection reports supported suspicious-pattern counts; the separate deterministic checkpoint renderer additionally redacts those supported patterns only in its derived handoff artifact.

See [`docs/privacy-model.md`](docs/privacy-model.md) and [`docs/deterministic-checkpoint.md`](docs/deterministic-checkpoint.md).

## Project origin

This project grew from a working proof of concept built to migrate a very long ChatGPT technical project. The PoC validated the need for snapshot checks, whitelist extraction, body-vs-runtime secret separation, hierarchical checkpoint compilation, and incremental state reuse. The public codebase is a clean-room modularization of those ideas; no private conversation fixture is included.

## Development

```bash
python -m unittest discover -s tests -v
```

CI also builds wheel + sdist and smoke-tests the installed wheel, including the installed `paic conform` and `paic checkpoint` commands, in an isolated environment before release work proceeds.

## Status

`0.1.0a2` is prepared as the next alpha release candidate. Package/release CI is in place, but the version is **not considered published** until the tagged publication/checksum workflow in Issue #18 is completed. APIs and schemas remain alpha and may change before 1.0.

## License

MIT.
