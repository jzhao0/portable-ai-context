# Roadmap

## v0.1 — Core portability alpha

- [x] Canonical conversation model
- [x] Clean HTML / compact TXT / JSONL adapters
- [x] ChatGPT saved HTML adapter
- [x] Privacy report
- [x] Integrity report
- [x] `.aicb` alpha bundle
- [x] OpenAI-compatible hierarchical migration compiler
- [x] CLI
- [x] Cross-platform unit-test matrix
- [x] Harden ChatGPT shared-URL capture across macOS / Windows / Linux
- [x] Synthetic/conformance fixtures for supported adapter subsets
- [x] Package CI that builds wheel + sdist and smoke-tests the installed wheel
- [ ] Publish the first tagged alpha with checksums / trusted publishing (#18)

## v0.2 — Source adapters

- [x] Claude local single-conversation JSON export subset
- [x] Gemini Apps Google My Activity JSON subset
- [ ] Validate deliberately non-sensitive real Claude/Gemini exports (#17)
- [ ] Claude shared/page adapter
- [ ] Gemini page/thread adapter when a reliable source contract exists
- [ ] DeepSeek chat adapter
- [ ] Grok adapter
- [x] Minimal generic browser DOM capture contract (`role_attribute_v1`)
- [x] Shared adapter conformance harness + content-free `paic conform` (#25)

## v0.3 — Better context compilation

- [x] Token-counter abstraction with injectable exact counters
- [x] Lite / Standard / Full migration profiles
- [ ] Bundled model-specific exact tokenizers
- [ ] Pluggable compiler backends
- [ ] Anthropic backend
- [ ] Gemini backend
- [ ] Ollama / local model backend
- [x] Deterministic no-AI extractive checkpoint mode (#27)

## v0.4 — Capture UX

- [x] Chromium browser extension MVP
- [x] Message-count + last-user/assistant preview before browser download
- [ ] Separate Chrome and Brave live smoke validation
- [ ] Firefox runtime/package validation
- [ ] Broader snapshot completeness UI
- [ ] Optional body-secret redaction review

## v0.5 — Handoff integrations

- [ ] MCP server
- [ ] Claude Code / Codex / Cursor handoff recipes
- [ ] `.aicb` import/export APIs

## v1.0 — Stable portability contract

- [ ] Stable canonical schema
- [ ] Stable `.aicb` bundle format
- [ ] Backward-compatibility policy
- [ ] Signed releases / checksums
- [ ] Cross-platform release matrix

See [`docs/release-readiness-0.1.0a2.md`](docs/release-readiness-0.1.0a2.md) for the distinction between synthetic CI coverage and real live evidence.
