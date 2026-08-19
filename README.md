# Portable AI Context

> **Working title / alpha.** Turn long AI conversations into privacy-aware, verifiable context packages another model can actually continue from.

**Export is not migration. Preserve the state, not the transcript.**

Portable AI Context (`paic`) is a local-first Python toolkit for extracting conversations from supported sources, normalizing them into a canonical schema, auditing privacy and completeness, exporting portable artifacts, and compiling long histories into migration prompts.

## Why

Long-running AI conversations accumulate decisions, corrections, commands, experiment results, preferences, and project state. Copying the raw transcript into a new model is often wasteful or impossible. Traditional exporters solve *serialization*; this project targets *handoff quality*.

The design goals are:

- **Portable:** source adapters normalize different conversation formats.
- **Privacy-aware:** runtime/session metadata is excluded by whitelist; body-secret detection warns without printing secret values; explicit redaction creates derived review copies rather than rewriting canonical history.
- **Verifiable:** counts, message hashes, conversation digest, snapshot metadata, and tail hashes make truncation visible.
- **Local-first:** extraction, normalization, inspection, conformance checking, deterministic checkpoint generation, pattern-limited redaction review, and bundle creation need no AI API.
- **Compiler-agnostic:** migration compilation uses a common backend protocol with built-in OpenAI-compatible, Anthropic, Gemini, and native Ollama transports.
- **Cross-platform:** the core and CLI are Python 3.10+ and avoid OS-specific dependencies.

## v0.1 alpha scope

### Inputs

- Migrator Clean HTML
- compact TXT (`<<<USER>>>` / `<<<ASSISTANT>>>`)
- JSONL (`role`, `text`)
- `.aicb` `0.1-alpha` bundles after strict in-memory structure/integrity validation
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
- pattern-limited derived redaction-review HTML/TXT/JSONL + content-free report
- optional migration prompt via OpenAI-compatible, Anthropic, Gemini, or Ollama compiler backend
- compile budget report with dependency-free estimates or an optional exact raw-text tiktoken counter

### Not yet promised

- Grok adapter
- automatic multi-conversation Claude archive selection
- Claude shared-page HTML adapter
- reconstruction of original Gemini chat-thread boundaries from flat My Activity exports
- localized Gemini activity prompt formats beyond the documented alpha subset
- universal/provider-native exact token counting across all compiler backends
- general-purpose DLP/PII sanitization beyond the documented pattern-limited redaction rules
- Firefox browser-capture support or signed browser-store distribution
- desktop GUI
- stable `.aicb` schema
- host-specific Claude Code / Codex / Cursor handoff recipes

Those belong on the roadmap, not in the v0.1 contract.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e .
```

The base install remains dependency-free. Optional local exact raw-text counting under OpenAI tiktoken encodings is available with:

```bash
pip install -e '.[tokenizers]'
```

Optional local MCP handoff support is available with:

```bash
pip install -e '.[mcp]'
```

The MCP alpha is stdio-only and requires an explicit workspace root:

```bash
paic mcp --root /path/to/workspace
```

It exposes only `inspect_source`, `conform_source`, `build_checkpoint`, and `build_redaction_review`. Source arguments are root-relative local PAIC sources, and generated artifacts are written only under the server-owned `.paic-mcp/` area. The MCP server does **not** expose arbitrary file reads/listing, raw conversation text, `paic compile`, provider/network calls, shell execution, or arbitrary output paths. PAIC enforces its own resolved-path root boundary and does not rely on MCP Roots as authorization. See [`docs/mcp-server.md`](docs/mcp-server.md).

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

Create an explicit pattern-limited redaction review without modifying the source/canonical conversation:

```bash
paic redact conversation.clean.html -o redaction-review
```

This writes derived redacted HTML/TXT/JSONL plus a content-free `redaction-report.json`. The report always keeps `manual_review_required=true` and `patterns_are_exhaustive=false`, even when the supported-pattern rescan is zero. A zero supported-pattern count is **not** proof that the artifact contains no other sensitive information. See [`docs/redaction-review.md`](docs/redaction-review.md) and [`docs/privacy-model.md`](docs/privacy-model.md).

Create a portable bundle:

```bash
paic bundle conversation.clean.html -o project.aicb
```

Reopen the bundle through the same source registry:

```bash
paic inspect project.aicb
paic verify project.aicb
paic conform project.aicb
paic checkpoint project.aicb -o checkpoint-from-bundle
```

The alpha reader validates the ZIP member contract, resource limits, canonical JSONL shape, manifest count/digest, integrity counts/tail hashes, and recomputable privacy-body counts before returning a canonical conversation. It never extracts archive members to arbitrary paths. SHA256 checks provide internal consistency, **not author authenticity or a digital signature**. See [`docs/aicb-bundle.md`](docs/aicb-bundle.md).

Verify integrity and tail metadata:

```bash
paic verify conversation.clean.html
```

Compile a semantic migration prompt using an OpenAI-compatible API:

```bash
export PAIC_API_KEY='...'
paic compile conversation.clean.html \
  --backend openai-compatible \
  --api-base https://api.example.com/v1 \
  --map-model fast-model \
  --final-model strong-model \
  --profile standard \
  -o migration
```

Or use the zero-dependency Anthropic Messages transport:

```bash
export ANTHROPIC_API_KEY='...'
paic compile conversation.clean.html \
  --backend anthropic \
  --api-key-env ANTHROPIC_API_KEY \
  --map-model <map-model> \
  --final-model <final-model> \
  --anthropic-max-tokens 4096 \
  --profile standard \
  -o migration
```

Or use the zero-dependency Gemini `generateContent` transport:

```bash
export GEMINI_API_KEY='...'
paic compile conversation.clean.html \
  --backend gemini \
  --api-key-env GEMINI_API_KEY \
  --map-model <map-model> \
  --final-model <final-model> \
  --gemini-max-output-tokens 4096 \
  --profile standard \
  -o migration
```

Or use native local Ollama with no API key by default:

```bash
paic compile conversation.clean.html \
  --backend ollama \
  --map-model <local-model> \
  --final-model <local-model> \
  --ollama-num-predict 4096 \
  --profile standard \
  -o migration
```

The Ollama backend defaults to `http://localhost:11434` and does not automatically reuse `PAIC_API_KEY`. Optional bearer authentication is explicit through `--ollama-api-key-env`. “Local backend” describes the default endpoint only: explicitly changing `--api-base` to a remote host can cause network access.

PAIC does not hardcode provider model names. See [`docs/compiler-backends.md`](docs/compiler-backends.md), [`docs/anthropic-backend.md`](docs/anthropic-backend.md), [`docs/gemini-backend.md`](docs/gemini-backend.md), and [`docs/ollama-backend.md`](docs/ollama-backend.md) for transport/configuration and error/privacy boundaries.

Named checkpoint/compiler budgets are `lite` (4,000), `standard` (16,000), and `full` (64,000) tokens. You can instead use `--budget <tokens>`. The default CLI counter remains a dependency-free character estimate. With the optional tokenizer extra installed, `--token-counter tiktoken` enables exact counting of the plain text passed to the compiler counter under a resolved tiktoken encoding; this is **not** a claim of exact provider request/billing tokens. Use `--tiktoken-encoding` for an explicit encoding or let tiktoken resolve `--tokenizer-model` / the final model when it recognizes that model. See [`docs/token-budgets.md`](docs/token-budgets.md).

For pages where direct capture is unreliable, the experimental Chromium browser extension uses only `activeTab` + `scripting`, previews message count and tail text before download, and exports canonical JSONL locally. See [`extension/README.md`](extension/README.md) and the [`browser-extension threat model`](docs/browser-extension-threat-model.md).

`paic` never requires API access for extraction, inspection, conformance checking, deterministic checkpoint generation, pattern-limited redaction review, verification, bundle creation/import, or the stdio-only MCP orchestration of those local operations. Only AI-assisted `paic compile` requires a model backend. The optional tiktoken counter performs tokenizer computation locally, although tiktoken itself may populate its encoding-data cache when an encoding is initialized.

## Verification status

The project distinguishes real live validation from synthetic/conformance coverage. ChatGPT shared-URL capture has real macOS, Windows, and Linux smoke evidence, and the browser extension has a real Windows Edge smoke. Claude and Gemini source adapters currently have synthetic fixtures plus cross-platform CI; deliberately non-sensitive real-export validation remains tracked in Issue #17.

The shared adapter conformance contract adds one common post-canonicalization gate for current and future adapters. It verifies canonical roles/indices/text, integrity consistency, and clean HTML / compact TXT / JSONL digest-preserving round trips, but it does **not** replace real provider-source validation.

The deterministic checkpoint and explicit `paic redact` review share one pattern-limited secret-redaction primitive. Both leave canonical history unchanged. Neither is a general confidentiality scrubber, and derived artifacts must be reviewed before sharing.

`.aicb` import recomputes canonical integrity rather than trusting the manifest/report at face value. The current strict `0.1-alpha` member contract and threat model are documented in [`docs/aicb-bundle.md`](docs/aicb-bundle.md). The schema remains unstable before 1.0.

Compiler transport tests are deterministic and do not spend live provider API keys in CI. Anthropic is validated against the Messages contract with mocked HTTP, Gemini against the stateless `generateContent` contract, and Ollama against native `/api/chat`. CI does not install/start Ollama or run model compute; a real local-model smoke is separate optional validation on a machine where Ollama was intentionally installed.

The package job first proves that the base built wheel does not install tiktoken or MCP, then explicitly installs optional extras from the **same built wheel**. It smoke-tests a real tiktoken encoding/model mapping and uses the official MCP SDK `Client(server)` in memory to verify exactly four PAIC tools, zero resources, content-free inspect/conform results, server-owned checkpoint/redaction writes, and content-safe traversal errors without starting a network listener. The base installed-wheel smoke also runs `paic redact` on a synthetic fake-secret fixture and verifies that the content-free report does not echo that fake secret. Provider-native token-count API coverage and host-specific MCP client recipes remain separate future work.

See [`docs/release-readiness-0.1.0a2.md`](docs/release-readiness-0.1.0a2.md) for the full evidence ledger and known alpha limitations.

## Canonical model

Every adapter produces a `Conversation` with:

- source metadata
- snapshot metadata when available
- ordered messages
- canonical roles
- per-message metadata

The initial bundle manifest schema is documented in [`schemas/conversation-bundle.schema.json`](schemas/conversation-bundle.schema.json), and the importer/trust contract in [`docs/aicb-bundle.md`](docs/aicb-bundle.md). Both are explicitly **alpha** and may change before 1.0.

## Privacy model

Two different classes of secrets are treated differently:

1. **Page/runtime secrets** — account/session/auth/bootstrap data that is not part of the conversation. Adapters use whitelists and do not emit it.
2. **Secrets typed into the conversation body** — these are user content. Canonical history is not silently rewritten. Privacy inspection reports supported suspicious-pattern counts. Explicit `paic redact` and deterministic checkpoint generation use the same pattern-limited derived-output transform, while still requiring manual review.

See [`docs/privacy-model.md`](docs/privacy-model.md), [`docs/redaction-review.md`](docs/redaction-review.md), and [`docs/deterministic-checkpoint.md`](docs/deterministic-checkpoint.md).

## Project origin

This project grew from a working proof of concept built to migrate a very long ChatGPT technical project. The PoC validated the need for snapshot checks, whitelist extraction, body-vs-runtime secret separation, hierarchical checkpoint compilation, and incremental state reuse. The public codebase is a clean-room modularization of those ideas; no private conversation fixture is included.

## Development

```bash
python -m unittest discover -s tests -v
```

CI also builds wheel + sdist and smoke-tests the installed wheel in an isolated environment. The package smoke covers normal JSONL loading, a real `bundle -> .aicb -> inspect/verify/conform/checkpoint` cycle, pattern-limited redaction review, packaged compiler-backend/token-counter/MCP CLI surfaces, proof that the base wheel remains tokenizer/MCP-free, a separate explicit optional-extra tiktoken smoke, and an official MCP SDK in-memory smoke installed from the same built wheel.

## Status

`0.1.0a2` is prepared as the next alpha release candidate. Package/release CI is in place, but the version is **not considered published** until the tagged publication/checksum workflow in Issue #18 is completed. APIs and schemas remain alpha and may change before 1.0.

## License

MIT.
