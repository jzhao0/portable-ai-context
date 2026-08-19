# 0.1.0a2 release-readiness ledger

This document records what Portable AI Context has actually verified before the `0.1.0a2` alpha publication step. It deliberately distinguishes deterministic/synthetic test coverage from real live capture evidence.

**Publication status:** release candidate only. `0.1.0a2` is not considered published until the tag/release/PyPI/checksum workflow in Issue #18 is completed and independently smoke-tested.

## Evidence classes

- **Real live smoke:** exercised against a real browser/provider page or a built distribution in an actual runtime.
- **Cross-platform CI:** deterministic repository tests on GitHub-hosted Ubuntu, Windows, and macOS.
- **Synthetic conformance:** parser/compiler behavior tested with deliberately artificial fixtures or fake backends/tokenizers.
- **Compatibility-only:** implemented from a documented/observed shape but not yet validated against a deliberately non-sensitive real export.

## Capability ledger

| Capability | Evidence | Current status / boundary |
| --- | --- | --- |
| Canonical conversation model, clean HTML/TXT/JSONL, integrity/privacy reports | Cross-platform CI + deterministic round-trip tests | Implemented. Alpha schema remains unstable. |
| ChatGPT shared-URL capture | **Real live smoke** on macOS and Windows against the same 425-message / 1773-raw-node snapshot; both used `direct_http` and produced identical digest/tail hashes. Separate GitHub-hosted Ubuntu live smoke used a deliberately public two-message share and also used `direct_http`. | Real macOS/Windows/Linux capture verified. Chromium-family browser fallback logic/discovery is CI-tested, but a live case that actually required `browser_fallback` has not been recorded. |
| ChatGPT saved/share HTML parsing | Deterministic fixtures/round-trip tests; project-origin PoC exercised real saved content but no private raw fixture is committed | Implemented; public repository intentionally contains no private source archive. |
| Claude local conversation JSON adapter | **Synthetic conformance** + cross-platform CI | Supported alpha subset. Deliberately non-sensitive real export validation is still open in Issue #17. No authenticated scraping/page adapter. |
| Gemini Apps My Activity JSON adapter | **Synthetic conformance** + cross-platform CI | Supported flat activity-stream subset. Deliberately non-sensitive real Takeout validation is still open in Issue #17. Original chat-thread reconstruction is not claimed. |
| Token-aware migration budgets and Lite/Standard/Full profiles | Deterministic fake exact-tokenizer/backend tests + cross-platform CI | Compiler accepts injectable exact counters. Dependency-free CLI uses an explicit character/token estimate unless the caller supplies an exact tokenizer. |
| Chromium browser capture extension | **Real live smoke** on Windows Edge using a deliberately public/non-sensitive two-message conversation; preview count/tail matched downloaded JSONL; `paic inspect`/`verify` reproduced the same canonical messages. | Edge real smoke verified. Chrome and Brave are first-target Chromium browsers but have not been separately live-smoke-tested. Firefox is feasibility-only. |
| Wheel/sdist packaging | **Real CI distribution smoke**: build wheel + sdist, install only the wheel into an isolated venv, verify distribution/package version, console script, `paic --help`, and `paic inspect`. | CI #25 passed with the existing 9 test jobs plus the package job. Publication is still separate. |

## Content-free real-smoke evidence

### ChatGPT macOS / Windows shared snapshot

Both machines captured the same private/reference share without publishing its URL or conversation text:

- canonical messages: `425`
- raw nodes: `1773`
- capture method: `direct_http`
- conversation digest: `cc9517430d3b243033c245589a47d02f7524cd6a508e4ef4e4833d01d5cdc29d`
- last user hash: `84395bdd362dc36b72d8556b4b0e4d2ae0a19d7fe52f8c359d4408df7bb8f895`
- last assistant hash: `fe2812f305dfd5e822560c916f1c7503bec8373f39fc12f2776abec42dbe0bc7`

### Chromium extension / Edge

The deliberately public/non-sensitive two-message smoke artifact produced:

- adapter: `role_attribute_v1`
- messages: `2` (`1` user, `1` assistant)
- ignored role nodes: `0`
- empty role nodes: `0`
- downloaded JSONL SHA256: `9ccfd76270638dc7496aec6945cfb697fffd074c97c0faf3223c88c05d8206ed`
- canonical digest after PAIC import: `1dffc50ddafa353d8658353a6eccde228520feeba40a5bd948d3e0e9a70ba214`
- runtime privacy markers: none
- supported body-secret counters: all zero

## Release-candidate gates

Before calling `0.1.0a2` published:

1. package/release CI must remain green (#15 completed);
2. repository version, package `__version__`, and `paic --version` must agree;
3. release notes must preserve the evidence boundaries above, especially Claude/Gemini real-export status;
4. publication must use a tagged commit and produce matching wheel/sdist checksums (#18);
5. a fresh install of the published artifact must pass `paic --version` and a local inspect smoke.

## Known alpha limitations

- Canonical and `.aicb` schemas are not stable contracts yet.
- Claude and Gemini real-export validation is pending Issue #17.
- ChatGPT browser fallback has deterministic coverage but no recorded live fallback-required smoke.
- Chromium extension DOM selectors are experimental and page markup can drift.
- The extension does not redact secrets deliberately typed into conversation text.
- Exact target-model tokenization is not bundled; exact counters are injectable through the Python API.
- Migration compilation still depends on an OpenAI-compatible backend when AI-assisted compilation is requested.

The release ledger should be updated when any of these evidence classes change; a synthetic test must never be silently relabeled as real provider validation.
