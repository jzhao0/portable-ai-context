# Changelog

## 0.1.0a2 — Unreleased

- Hardened ChatGPT shared-URL capture and normalized share-input handling.
- Added cross-platform Chromium-family browser discovery and isolated browser fallback.
- Added content-free live smoke reporting with capture-method evidence.
- Completed real ChatGPT shared-URL smoke validation on macOS, Windows, and Linux.
- Added a local-only Claude single-conversation JSON adapter with strict allowlisting and synthetic conformance fixtures.
- Added a conservative Gemini Apps / Google My Activity JSON adapter with explicit thread-reconstruction limitations.
- Added token-counter abstraction, Lite/Standard/Full migration profiles, explicit token budgets, compile reports, and budget-overrun reporting.
- Added an experimental Chromium Manifest V3 capture extension using only `activeTab` + `scripting`, with preview-before-download and canonical JSONL export.
- Completed a real Windows Edge extension smoke from DOM capture through `paic inspect` / `verify` / privacy scan.
- Added package CI that builds wheel + sdist, installs only the built wheel into an isolated environment, and smoke-tests the installed `paic` distribution.
- Modernized package license metadata to PEP 639 SPDX form.
- Added `paic --version` and a release-readiness ledger distinguishing real evidence from synthetic/compatibility-only coverage.

### Known alpha gaps

- Real deliberately non-sensitive Claude/Gemini export validation is still pending.
- ChatGPT browser fallback is CI-tested but has not yet been captured in a live fallback-required case.
- Chrome/Brave and Firefox extension runtime validation are not yet complete.
- Exact target-model tokenizers are injectable but not bundled.
- Canonical and `.aicb` schemas remain unstable alpha contracts.

`0.1.0a2` is not considered published until the tagged publication/checksum workflow is completed.

## 0.1.0a1 — 2026-08-18

- Initial public architecture bootstrap.
- Added canonical conversation model.
- Added clean HTML, compact TXT, JSONL, and ChatGPT saved HTML adapters.
- Added privacy and integrity reporting.
- Added alpha `.aicb` bundle writer.
- Added OpenAI-compatible hierarchical migration compiler.
- Added cross-platform CLI and local unit tests.
