# Roadmap

## v0.1 — Core portability alpha

- [x] Canonical conversation model
- [x] Clean HTML / compact TXT / JSONL adapters
- [x] ChatGPT saved HTML adapter
- [x] Privacy report
- [x] Integrity report
- [x] `.aicb` alpha bundle writer
- [x] `.aicb` first-class strict reader / verifier (#29)
- [x] OpenAI-compatible hierarchical migration compiler
- [x] CLI
- [x] Cross-platform unit-test matrix
- [x] Harden ChatGPT shared-URL capture across macOS / Windows / Linux
- [x] Synthetic/conformance fixtures for supported adapter subsets
- [x] Package CI that builds wheel + sdist and smoke-tests the installed wheel
- [x] Publish the first tagged alpha with checksums / trusted publishing (#18)

## v0.2 — Source adapters

- [x] Claude local single-conversation JSON export subset
- [x] Gemini Apps Google My Activity JSON subset
- [ ] Validate deliberately non-sensitive real Claude/Gemini exports (#17)
- [ ] Claude shared/page adapter
- [ ] Gemini page/thread adapter when a reliable source contract exists
- [ ] DeepSeek chat adapter (#58)
- [ ] Grok adapter
- [x] Minimal generic browser DOM capture contract (`role_attribute_v1`)
- [x] Shared adapter conformance harness + content-free `paic conform` (#25)

## v0.3 — Better context compilation

- [x] Token-counter abstraction with injectable exact counters
- [x] Lite / Standard / Full migration profiles
- [x] Optional local exact tiktoken raw-text counter (#41)
- [x] Provider-native token-count adapters where semantics are trustworthy (#60)
- [x] Pluggable compiler backend registry / CLI boundary (#31)
- [x] Anthropic Messages backend (#33)
- [x] Gemini generateContent backend (#35)
- [x] Ollama / local model backend (#37)
- [x] Deterministic no-AI extractive checkpoint mode (#27)

## v0.4 — Capture UX

- [x] Chromium browser extension MVP
- [x] Message-count + last-user/assistant preview before browser download
- [ ] Separate Chrome and Brave live smoke validation
- [ ] Firefox runtime/package validation
- [ ] Broader snapshot completeness UI
- [x] Pattern-limited body-secret redaction review (#43)

## v0.5 — Handoff integrations

- [x] MCP server (#46)
- [x] Claude Code / Codex / Cursor handoff recipes (#49)
- [x] `.aicb` import/export core APIs (#29)

## v1.0 — Stable portability contract

- [ ] Stable canonical schema
- [ ] Stable `.aicb` bundle format
- [ ] Backward-compatibility policy
- [ ] Signed releases / checksums
- [ ] Cross-platform release matrix

See [`docs/release-readiness-0.1.0a2.md`](docs/release-readiness-0.1.0a2.md) for the distinction between synthetic CI coverage and real live evidence.
