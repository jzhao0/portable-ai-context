# Deterministic no-AI extractive checkpoints

`paic checkpoint` builds a local, reproducible handoff artifact without calling an LLM, embeddings API, tokenizer service, or network endpoint.

It is deliberately **extractive rather than semantic**. The tool selects and, when necessary, excerpts source messages according to a fixed policy. It does not claim to understand which statement is correct, current, completed, or superseded.

Use the AI-assisted `paic compile` path when semantic compression and state reconciliation are required. Use `paic checkpoint` when zero-API operation, auditability, and deterministic evidence are more important than semantic compression quality.

## Quick start

```bash
paic checkpoint conversation.clean.html -o checkpoint
```

This writes:

```text
checkpoint/
├── CHECKPOINT.md
└── checkpoint-report.json
```

No API key is required.

The default target is the existing `standard` budget profile:

```text
standard = 16,000 estimated tokens
```

Named profiles are shared with the AI compiler:

```bash
paic checkpoint conversation.clean.html -o checkpoint --profile lite
paic checkpoint conversation.clean.html -o checkpoint --profile standard
paic checkpoint conversation.clean.html -o checkpoint --profile full
```

Current profile targets are:

```text
lite      4,000
standard 16,000
full     64,000
```

An explicit budget can be used instead:

```bash
paic checkpoint conversation.clean.html -o checkpoint --budget 8000
```

The dependency-free CLI uses the same explicit character/token estimate as the compiler fallback. `--chars-per-token` can adjust that estimate. The Python API can receive an exact `TokenCounter` implementation.

## Policy: `deterministic-extractive-v1`

Selection uses a fixed priority order:

1. the latest user message;
2. the latest assistant message;
3. the first user message as an original-goal anchor;
4. additional recent tail messages;
5. older messages containing explicit state-marker vocabulary;
6. additional recent messages if unused budget remains.

The selected blocks are always rendered back into **source chronological order**, even though candidate selection is priority-based.

The state-marker vocabulary is intentionally small and mechanical. It recognizes explicit English terms such as `TODO`, `next`, `pending`, `blocker`, `error`, `passed`, `verified`, `version`, `commit`, `constraint`, `must`, and `next action`, plus a small documented Chinese set including terms such as `下一步`, `待办`, `未完成`, `阻塞`, `等待`, `失败`, `通过`, `验证`, `版本`, `提交`, `必须`, `隐私`, `安全`, and `继续`.

A marker match only affects selection priority. It does **not** mean PAIC has classified the statement as true, unresolved, or current.

## Message evidence and hashes

Each selected block records:

```text
source_index
source_message_sha256
selection_reason
state_marker_hits
```

`source_message_sha256` is the deterministic integrity hash of the **original canonical role + message text**, before derived-artifact redaction or excerpting. This lets the checkpoint refer back to canonical history even when the rendered excerpt is shortened or a supported secret-like value is removed.

The hash is a one-way integrity fingerprint, but users should still treat checkpoint artifacts as derived from the original conversation and review them before public sharing.

The local source path / locator is never copied into `CHECKPOINT.md` or `checkpoint-report.json`.

## Explicit excerpting, never silent truncation

A selected long message can be shortened only when necessary to satisfy the configured checkpoint budget. The alpha policy keeps both head and tail evidence and inserts an explicit marker:

```text
[PAIC DETERMINISTIC OMISSION: 1234 CHARACTERS OMITTED]
```

A truncated selected message must retain actual source-derived characters in addition to the omission marker. If the current phase budget cannot fit a minimum useful excerpt, that candidate is skipped instead of emitting an omission-only placeholder.

The report records `truncated_message_count`.

## Derived-artifact secret redaction

Canonical conversation history is **not changed** by checkpoint generation.

Before selected message text is rendered into `CHECKPOINT.md`, PAIC replaces the secret-like body patterns currently recognized by the privacy layer:

- OpenAI-style `sk-...` keys;
- GitHub token patterns recognized by PAIC;
- AWS access-key IDs recognized by PAIC;
- long `Bearer ...` token patterns;
- private-key material beginning with supported private-key PEM headers.

Replacement markers look like:

```text
[REDACTED:github_token]
[REDACTED:private_key_material]
```

`checkpoint-report.json` records only category counts. It never records matched secret values.

### Important limitation

This is **best-effort pattern redaction, not a general confidentiality scrubber**. It does not automatically remove every possible:

- name;
- email address;
- private URL;
- account identifier;
- business secret;
- confidential prose;
- credential format not covered by the current patterns.

Review `CHECKPOINT.md` before sending it to another person or publishing it.

## Reproducibility report

`checkpoint-report.json` contains content-free generation metadata including:

```text
policy
source_kind
source_message_count
source_conversation_digest
selected_message_count
selected_indices
first_user_included
latest_user_included
latest_assistant_included
truncated_message_count
redaction_counts
tokenizer
tokenizer_exact
profile
budget_tokens
source_token_estimate
output_token_estimate
compression_ratio
budget_met
```

It intentionally omits source path, conversation title, message text, tail text, and matched secret values.

For the same canonical source, policy version, budget/profile, and token-counter behavior, PAIC writes byte-identical `CHECKPOINT.md` and `checkpoint-report.json`. No wall-clock timestamp is embedded in either file.

## Conformance gate

Checkpoint generation first runs the shared canonical conformance contract in memory. A source that loads but produces an invalid canonical conversation is rejected with a content-free error directing the user to:

```bash
paic conform <source>
```

This keeps no-AI handoff generation downstream of the same role/index/text/round-trip invariants used for adapters.

## Checkpoint vs AI migration compilation

| Property | `paic checkpoint` | `paic compile` |
| --- | --- | --- |
| Network/API required | No | Yes, for AI-assisted compilation |
| Deterministic for same inputs | Yes | Model/backend dependent |
| Uses source excerpts | Yes | Uses model-generated checkpoint notes/prompt |
| Reconciles newer vs older state semantically | No | Designed to do so |
| Can infer continuation-critical meaning | No | Model-assisted |
| Secret-like derived-output handling | Pattern redaction | Compiler prompts instruct model not to reproduce secrets; review still required |
| Auditability back to source messages | Explicit indices + hashes | Via compiler state/notes, not a pure extractive mapping |

The two modes are complementary. A deterministic extractive checkpoint is a safe fallback/evidence artifact, not a replacement for semantic migration compilation.