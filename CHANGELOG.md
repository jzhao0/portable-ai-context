# Changelog

## 0.1.0a2 — 2026-08-19

### Core portability and verification

- Added a strict first-class `.aicb` `0.1-alpha` reader/verifier in addition to the existing writer, with archive/member limits, canonical JSONL validation, manifest/integrity/privacy consistency checks, and installed-wheel bundle round-trip smoke coverage.
- Added the shared content-free `paic conform` gate for canonical structure, integrity consistency, and clean HTML / compact TXT / JSONL round-trip verification.
- Expanded installed-distribution smoke coverage across source inspection, conformance, `.aicb` round trips, deterministic checkpoints, redaction review, optional tokenizer support, and optional MCP support.
- Integrity hashes/digests remain internal consistency and truncation/tamper evidence only; they are not author authenticity or digital signatures.

### Source adapters and capture

- Hardened ChatGPT shared-URL capture and normalized share-input handling.
- Added cross-platform Chromium-family browser discovery and isolated fresh-profile browser fallback.
- Added content-free live smoke reporting with capture-method evidence.
- Completed real ChatGPT shared-URL direct-capture smoke validation on macOS, Windows, and Linux. Browser-fallback-required live evidence remains separate.
- Added a local-only Claude single-conversation JSON adapter with strict allowlisting and synthetic/conformance fixtures.
- Added a conservative Gemini Apps / Google My Activity JSON adapter with explicit flat-activity/thread-reconstruction limitations and synthetic/conformance fixtures.
- Added a privacy-safe real-export probe workflow for deliberately non-sensitive Claude/Gemini volunteer validation without publishing raw provider archives.
- Added an experimental Chromium Manifest V3 capture extension using only `activeTab` + `scripting`, with message-count/tail preview before canonical JSONL download.
- Completed a real Windows Edge extension smoke from DOM capture through `paic inspect`, `verify`, and privacy checks.

### Local derived workflows and privacy

- Added deterministic no-AI `paic checkpoint` generation with Lite/Standard/Full budgets, reproducibility metadata, latest-state prioritization, and explicit limits on semantic truth resolution.
- Added explicit pattern-limited `paic redact` review artifacts and a content-free structural report without mutating canonical history.
- Unified deterministic checkpoint and explicit redaction review on one secret-redaction primitive, including whole private-key-material handling.
- Redaction remains deliberately non-exhaustive: `manual_review_required=true` and `patterns_are_exhaustive=false` remain mandatory even when supported-pattern rescanning returns zero.

### Context compilation and tokenization

- Added a pluggable compiler backend registry while keeping `compile_migration()` provider-agnostic.
- Added built-in OpenAI-compatible, Anthropic Messages, Gemini `generateContent`, and native Ollama `/api/chat` compiler transports.
- Added Ollama localhost/key-isolation and API-base validation hardening; localhost remains keyless by default while an explicit custom API base may be remote.
- Added token-counter abstraction, Lite/Standard/Full migration profiles, explicit token budgets, compile reports, and budget-overrun reporting.
- Added optional `portable-ai-context[tokenizers]` support for reviewed tiktoken 0.13.x raw-text/encoding-exact counting while keeping the base install dependency-free.
- Tiktoken exactness is limited to the plain text under the resolved encoding; exact provider request/billing token counts are not claimed.
- Anthropic, Gemini, and Ollama transport tests use deterministic/mocked provider contracts in CI; no live paid-provider/model execution is claimed by those tests.

### MCP and handoff integrations

- Added optional `portable-ai-context[mcp]` support using the official Python MCP SDK v2 while keeping the base wheel MCP-free.
- Added `paic mcp --root <workspace>` as a stdio-only, root-confined local server exposing exactly `inspect_source`, `conform_source`, `build_checkpoint`, and `build_redaction_review` with zero MCP resources.
- MCP source access remains root-relative and containment-checked; generated artifacts are restricted to fresh server-owned `.paic-mcp/` directories. MCP Roots are not used as PAIC authorization.
- The MCP alpha deliberately exposes no arbitrary file read/list, raw conversation resource, `paic compile`, provider/network call, shell execution, arbitrary output path, or remote HTTP/SSE service.
- Added conservative Claude Code, Codex, and Cursor handoff recipes with inert examples and static configuration/security tests.
- MCP SDK in-memory tests and host recipe static tests are not live Claude Code/Codex/Cursor host-validation evidence.

### Packaging and release readiness

- Added package CI that builds wheel + sdist, installs only the built wheel into an isolated environment, and smoke-tests the installed `paic` distribution.
- Base-wheel smoke explicitly verifies that optional tiktoken and MCP dependencies are absent until their extras are installed from the same built wheel.
- Modernized package license metadata to PEP 639 SPDX form.
- Added `paic --version` and a release-readiness ledger that separates real live evidence from synthetic, mocked, in-memory, static-configuration, and compatibility-only coverage.
- Added a fail-closed alpha publication pipeline with PyPI Trusted Publishing/OIDC, immutable tag/version/changelog checks, wheel/sdist validation, `SHA256SUMS`, post-publication PyPI hash comparison, fresh published-install smoke, and GitHub Release creation only after verification.
- The publication pipeline is implemented, but no `0.1.0a2` release tag, PyPI publication, or GitHub Release is claimed here; live publication remains gated by Issue #18.

### Known alpha gaps

- Deliberately non-sensitive real Claude/Gemini provider-export validation is still pending in Issue #17, with volunteer paths in Issues #22 and #24.
- ChatGPT browser fallback is CI-tested but has no recorded live case that actually required the browser fallback path.
- Separate Chrome and Brave extension live smoke validation is pending; Firefox runtime/package validation also remains pending.
- Provider-native token-count semantics are incomplete; optional tiktoken support does not represent exact provider request/billing counts.
- No real Ollama daemon/model execution smoke is recorded in the release evidence ledger.
- Claude Code, Codex, and Cursor handoff recipes have official-doc-aligned static configuration coverage, not an all-three-host live MCP smoke.
- Canonical and `.aicb` schemas remain unstable alpha contracts.
- Pattern-limited checkpoint/redaction secret removal is not general DLP/PII sanitization and still requires manual review.
- `0.1.0a2` remains unpublished until the tagged publication/checksum workflow in Issue #18 is completed.

## 0.1.0a1 — 2026-08-18

- Initial public architecture bootstrap.
- Added canonical conversation model.
- Added clean HTML, compact TXT, JSONL, and ChatGPT saved HTML adapters.
- Added privacy and integrity reporting.
- Added alpha `.aicb` bundle writer.
- Added OpenAI-compatible hierarchical migration compiler.
- Added cross-platform CLI and local unit tests.
