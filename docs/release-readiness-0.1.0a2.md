# 0.1.0a2 release-readiness ledger

This document records what Portable AI Context has actually verified before the `0.1.0a2` alpha publication step. It deliberately distinguishes deterministic/synthetic test coverage from real live capture/provider evidence.

**Publication status:** release candidate only. `0.1.0a2` is not considered published until the tag/release/PyPI/checksum workflow in Issue #18 is completed and independently smoke-tested.

Current version alignment remains:

```text
pyproject.toml project.version = 0.1.0a2
portable_ai_context.__version__ = 0.1.0a2
```

The installed-wheel package smoke also verifies that `paic --version` matches the distribution/package version.

## Evidence classes

- **Real live smoke:** exercised against a real browser/provider page or a built distribution in an actual runtime.
- **Cross-platform CI:** deterministic repository tests on GitHub-hosted Ubuntu, Windows, and macOS.
- **Synthetic / mocked contract coverage:** parser/compiler behavior tested with deliberately artificial fixtures, fake backends/tokenizers, mocked provider HTTP, or an in-memory protocol client/server.
- **Official-doc-aligned static configuration coverage:** committed host configuration examples are parsed or strictly shape-checked against current official host documentation, without launching the third-party host binary.
- **Compatibility-only:** implemented from a documented/observed source shape but not yet validated against a deliberately non-sensitive real provider export.

These labels are not interchangeable. Mocked provider HTTP proves PAIC request/response handling, not that a current paid provider account accepted a real request. An in-memory MCP SDK smoke proves SDK schema/dispatch compatibility, not that a specific external MCP host has launched the server successfully. Static host recipe validation proves the committed configuration shape, not a live Claude Code/Codex/Cursor connection.

## Capability ledger

| Capability | Evidence | Current status / boundary |
| --- | --- | --- |
| Canonical conversation model, clean HTML/TXT/JSONL, integrity/privacy reports | Cross-platform CI + deterministic round-trip tests | Implemented. Canonical schema remains alpha/unstable. |
| `.aicb` `0.1-alpha` writer + strict first-class reader/verifier | Cross-platform CI + installed-wheel `bundle -> .aicb -> inspect/verify/conform/checkpoint` smoke | Implemented. Reader validates archive/member limits, canonical JSONL, manifest/integrity/privacy consistency and does not extract members to arbitrary paths. SHA256/digests provide internal consistency/tamper visibility, **not author authenticity or a digital signature**. |
| Deterministic no-AI checkpoint mode | Cross-platform CI + deterministic reproducibility/budget tests + installed-wheel checkpoint smoke | Implemented as an extractive/reproducible fallback. It is not a semantic truth-resolution engine. Its derived secret redaction uses the same shared pattern-limited primitive as explicit redaction review. |
| Pattern-limited body-secret redaction review | Deterministic synthetic secret fixtures + derived-format digest round trips + installed-wheel fake-secret smoke (PR #44, final CI #97) | Explicit `paic redact` creates derived redacted HTML/TXT/JSONL plus a content-free structural report and never mutates canonical history. Original title/source locator/message metadata are not propagated. `supported_patterns_remaining=0` does **not** mean safe to share: `manual_review_required=true` and `patterns_are_exhaustive=false` remain mandatory. This is not general DLP/PII sanitization. |
| ChatGPT shared-URL capture | **Real live smoke** on macOS and Windows against the same 425-message / 1773-raw-node snapshot; both used `direct_http` and produced identical digest/tail hashes. Separate GitHub-hosted Ubuntu live smoke used a deliberately public two-message share and also used `direct_http`. | Real macOS/Windows/Linux direct capture verified. Chromium-family browser fallback logic/discovery is CI-tested, but no recorded live case has required `browser_fallback`. |
| ChatGPT saved/share HTML parsing | Deterministic fixtures/round-trip tests; project-origin PoC exercised real saved content but no private raw fixture is committed | Implemented; public repository intentionally contains no private source archive. |
| Claude local conversation JSON adapter | **Synthetic conformance** + cross-platform CI | Supported alpha subset. Deliberately non-sensitive real export validation is still open in Issue #17 / volunteer Issue #22. No authenticated scraping/page adapter. |
| Gemini Apps My Activity JSON adapter | **Synthetic conformance** + cross-platform CI | Supported flat activity-stream subset. Deliberately non-sensitive real Takeout validation is still open in Issue #17 / volunteer Issue #24. Original chat-thread reconstruction is not claimed. |
| Shared adapter conformance gate | Cross-platform CI + installed-wheel `paic conform` smoke | Implemented. Verifies canonical structure, integrity consistency, and clean HTML/TXT/JSONL round-trip behavior without printing conversation text; does not replace real provider-source validation. |
| Root-confined stdio MCP server alpha | Cross-platform root-policy/unit tests + official Python MCP SDK v2 `Client(server)` installed-wheel in-memory smoke (PR #47, final CI #110) | Optional `portable-ai-context[mcp]`; base wheel remains MCP-free. `paic mcp --root <workspace>` explicitly uses stdio, exposes exactly `inspect_source`, `conform_source`, `build_checkpoint`, and `build_redaction_review`, exposes no resources, confines sources to root-relative allowed local PAIC files, and writes only fresh server-owned artifacts under `.paic-mcp/`. MCP Roots are not used as authorization. No host-specific Claude Code/Codex/Cursor live integration or remote MCP deployment is claimed. |
| Claude Code / Codex / Cursor MCP handoff recipes | **Official-doc-aligned static configuration coverage** + dependency-free JSON/TOML shape/security tests (Issue #49) | Inert examples launch only `paic mcp --root ...` and do not add remote URLs, credentials, shell wrappers, or active repository-level self-install configuration. Cursor's project example uses documented `${workspaceFolder}` interpolation. Claude project configuration retains workspace trust/approval semantics. Codex uses its documented STDIO CLI/TOML shape. This is not live-host evidence. |
| Token-aware migration budgets and Lite/Standard/Full profiles | Deterministic fake exact-tokenizer/backend tests + cross-platform CI | Compiler accepts injectable counters. Dependency-free CLI defaults to the character estimate. |
| Optional local tiktoken raw-text counter | Deterministic lazy-import/model-resolution tests + package-job optional-extra smoke | Base wheel remains tokenizer-free. `portable-ai-context[tokenizers]` installs the reviewed tiktoken 0.13.x line. Exactness means exact plain-text tokenization under the resolved encoding, **not exact provider request/billing tokens**. PAIC delegates model mapping to tiktoken and does not guess unknown mappings. |
| Compiler backend registry / construction seam | Cross-platform CI + installed-wheel `paic compile --help` surface | Implemented. Built-ins currently include `openai-compatible`, `anthropic`, `gemini`, and `ollama`; `compile_migration()` remains provider-agnostic. |
| OpenAI-compatible compiler transport | Deterministic/mocked transport tests + cross-platform CI | Implemented. This ledger does not claim live-provider compiler evidence. |
| Anthropic Messages compiler transport | **Mocked provider HTTP** + cross-platform CI (PR #34, final CI #76) + installed-wheel CLI surface | Implemented using the documented non-streaming Messages contract. No live paid Anthropic call is claimed. |
| Gemini `generateContent` compiler transport | **Mocked provider HTTP** + cross-platform CI (PR #36, final CI #81) + installed-wheel CLI surface | Implemented using the stateless REST completion contract. No live paid Gemini call is claimed. |
| Native Ollama `/api/chat` compiler transport | **Mocked provider HTTP** + cross-platform CI (PR #38, final CI #90) + installed-wheel CLI surface | Implemented. Defaults to keyless `http://localhost:11434`, while explicit custom `--api-base` may access a remote host. CI does not install/start Ollama, pull a model, or run model compute; no real local-model smoke is claimed. |
| Chromium browser capture extension | **Real live smoke** on Windows Edge using a deliberately public/non-sensitive two-message conversation; preview count/tail matched downloaded JSONL; `paic inspect`/`verify` reproduced the same canonical messages. | Edge real smoke verified. Chrome and Brave are first-target Chromium browsers but have not been separately live-smoke-tested. Firefox is feasibility-only. |
| Wheel/sdist packaging | **Real CI distribution smoke**: build wheel + sdist, install only the wheel into an isolated venv, verify distribution/package/CLI version, source inspect/conform, `.aicb` roundtrip, deterministic checkpoint, pattern-limited `paic redact` fake-secret review, packaged compiler/token-counter/MCP CLI surfaces, then explicitly install/smoke tokenizer and MCP extras from the same built wheel | The base-wheel smoke verifies both tiktoken and MCP are absent before optional extras are installed. Redaction smoke verifies the synthetic secret is absent from stdout/report, supported-pattern rescan is zero, and manual review remains required. The MCP extra smoke uses the official SDK in memory and starts no listener. Publication remains separate. |

## Recent implementation evidence anchors

The release candidate has continued to evolve after the older package baseline. The current ledger includes these implementation slices:

- Issue #27 / PR #28 — deterministic no-AI extractive checkpoint mode.
- Issue #29 / PR #30 — `.aicb` first-class strict reader/verifier and installed-wheel roundtrip.
- Issue #31 / PR #32 — pluggable compiler backend registry / CLI construction boundary.
- Issue #33 / PR #34 — Anthropic Messages backend; final CI #76 passed 10/10 jobs.
- Issue #35 / PR #36 — Gemini `generateContent` backend; final CI #81 passed 10/10 jobs.
- Issue #37 / PR #38 — native Ollama backend and URL/key-isolation hardening; final CI #90 passed 10/10 jobs.
- Issue #41 / PR #42 — optional tiktoken raw-text exact counter while preserving the zero-dependency base install; final CI #95 passed 10/10 jobs.
- Issue #43 / PR #44 — pattern-limited explicit body-secret redaction review sharing one redaction primitive with deterministic checkpoint generation; final CI #97 passed 10/10 jobs.
- Issue #46 / PR #47 — stdio-only root-confined MCP server alpha; final CI #110 passed 10/10 jobs and squash-merged as `a28d8aa223a1ad5388d684e36738bc9623dd500f`.
- Issue #49 — official-current Claude Code, Codex, and Cursor MCP handoff recipes with inert examples and static configuration/security contract tests. Live host evidence is intentionally separate.

The current merged `main` anchor before the Issue #49 handoff-recipe branch is:

```text
a28d8aa223a1ad5388d684e36738bc9623dd500f
```

Commit identifiers are implementation anchors, not release tags.

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

1. package/release CI must remain green;
2. repository version, package `__version__`, and `paic --version` must agree at `0.1.0a2`;
3. release notes must preserve the evidence boundaries above, especially Claude/Gemini real-export status and mocked-vs-live compiler transport status;
4. publication must use a tagged commit and produce matching wheel/sdist checksums (#18);
5. a fresh install of the **published** artifact must pass `paic --version` and a local inspect smoke;
6. no release note may describe `.aicb` digests as signing/authenticity evidence;
7. no mocked/synthetic/provider-in-memory/static-host-config result may be relabeled as a live provider/host validation;
8. optional tokenizer support must not make tiktoken an unconditional base dependency or be described as exact whole-request billing tokenization;
9. a redaction report with zero remaining **supported** patterns must never be described as proof that the artifact is generally safe to share; manual review remains required;
10. optional MCP support must not make the MCP SDK an unconditional base dependency, and in-memory SDK evidence must not be described as a host-specific Claude Code/Codex/Cursor live smoke or remote-service deployment;
11. handoff recipe examples must remain inert/reviewable and must not silently auto-install/approve PAIC in a cloned repository or introduce remote URLs/credentials into the stdio recipe.

## Known alpha limitations

- Canonical and `.aicb` schemas are not stable contracts yet.
- `.aicb` integrity/digests do not authenticate the bundle author and are not a signature system.
- Claude and Gemini real-export validation is pending Issue #17 (with volunteer Issues #22 and #24).
- ChatGPT browser fallback has deterministic coverage but no recorded live fallback-required smoke.
- Chromium extension DOM selectors are experimental and page markup can drift.
- Chrome and Brave have not been separately live-smoke-tested for the extension; Firefox remains unvalidated.
- The extension does not redact secrets deliberately typed into conversation text.
- Deterministic checkpoint and explicit redaction-review secret removal are **pattern-limited**, not general confidentiality/DLP/PII sanitization. Unknown credentials, PII, private URLs, proprietary prose, and unsupported secret formats may remain.
- `paic redact` deliberately requires manual review even when its supported-pattern rescan is zero; the implemented pattern set is explicitly non-exhaustive.
- Optional tiktoken exactness is raw-text/encoding exactness only; exact provider request/billing counts are not claimed.
- PAIC does not maintain speculative model-to-encoding mappings. Unknown tiktoken model mappings require an explicit encoding.
- Provider-native token-count adapters for Anthropic/Gemini/Ollama semantics remain future work; Anthropic's documented count is itself an estimate, Gemini counting is provider-side, and Ollama has no universal count-only native chat tokenizer endpoint.
- Anthropic, Gemini, and Ollama compiler transports have deterministic/mocked contract coverage, not live provider/model execution evidence in this ledger.
- The Ollama backend is local only by default; a caller-selected remote `--api-base` can cause network access.
- No real Ollama daemon/model smoke is recorded here.
- MCP transport is stdio-only in this alpha; no Streamable HTTP/SSE listener or remote authentication system is provided.
- MCP Roots are not an authorization boundary in PAIC. The launch-time `--root` and PAIC's own resolved-path confinement are the security boundary.
- The MCP alpha exposes no arbitrary file/resource read, no compile/provider/network tool, and no arbitrary output path. Generated checkpoint/redaction content remains on disk under server-owned `.paic-mcp/` directories rather than being returned as raw MCP resource text.
- Claude Code, Codex, and Cursor recipes are aligned to current official configuration documentation and statically tested, but no all-three-host live MCP integration smoke is recorded here.
- Third-party host configuration formats can change independently of PAIC; recipes must be rechecked against official documentation when evidence changes.
- `0.1.0a2` remains unpublished until Issue #18 is completed.

The release ledger should be updated whenever an evidence class changes. A synthetic, mocked, in-memory, or static-configuration test must never be silently relabeled as real provider/host validation.
