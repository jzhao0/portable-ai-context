# Pattern-limited body-secret redaction review

`paic redact` creates a **derived review copy** of a canonical conversation. It never rewrites the source file or canonical message history.

## Quick start

```bash
paic redact conversation.clean.html -o redaction-review
```

Output:

```text
redaction-review/
├── conversation.redacted.clean.html
├── conversation.redacted.compact.txt
├── conversation.redacted.jsonl
└── redaction-report.json
```

The three text artifacts contain the same derived user/assistant message sequence. Their canonical message digest is recorded as `redacted_conversation_digest` in the report.

## What is redacted

The explicit review command and deterministic checkpoint generation use the same shared pattern-limited transform.

Current covered categories include the body-secret patterns already recognized by PAIC, such as supported OpenAI-style keys, GitHub tokens, AWS access-key IDs, long bearer tokens, and supported private-key PEM material.

A private-key block is replaced as a whole rather than only masking its header.

Replacement markers are deterministic, for example:

```text
[REDACTED:openai_style_key]
[REDACTED:private_key_material]
```

Matched secret values are never copied into the report.

## Canonical history is not changed

The operation is derived-only:

```text
source
  ↓
canonical Conversation   (unchanged)
  ↓
pattern-limited transform
  ↓
review artifacts + report
```

The derived review conversation deliberately uses a generic title and does not carry over the original source locator or message metadata. This avoids leaking a private title/path after body text has been masked.

The source conversation digest in the report is computed before redaction. The redacted digest is computed from the derived role/text sequence. These hashes provide deterministic provenance/integrity linkage, not author authenticity or a digital signature.

## Content-free report

`redaction-report.json` contains structural evidence only:

```text
policy
source_kind
source_message_count
source_conversation_digest
redacted_conversation_digest
affected_message_count
total_redaction_counts
affected_messages
supported_patterns_remaining
manual_review_required
patterns_are_exhaustive
original_title_preserved
source_locator_preserved
```

For each affected message, the report may include:

```text
index
role
source_message_sha256
redaction_counts
```

It intentionally omits:

- matched values;
- original/redacted message previews;
- original conversation title;
- source file path/share URL;
- account/session/bootstrap data;
- message metadata.

## Manual review is always required

A normal successful report may say:

```json
{
  "supported_patterns_remaining": 0,
  "manual_review_required": true,
  "patterns_are_exhaustive": false
}
```

These three fields belong together.

`supported_patterns_remaining = 0` means only that **the patterns currently implemented by PAIC did not match the derived body after transformation**. It does not prove absence of:

- arbitrary passwords;
- email addresses or names;
- private URLs;
- account IDs;
- proprietary/confidential prose;
- credentials in unrecognized formats;
- new provider-specific secret formats;
- any other sensitive information outside the current pattern set.

Therefore `paic redact` is **not** a general DLP scanner or universal sanitizer. Review the redacted artifacts before sharing them.

## Relationship to `paic inspect`

`paic inspect` reports counts of the supported body-secret patterns on canonical history and does not mutate content.

`paic redact` is an explicit request to create a derived review copy. The original source remains unchanged.

You can inspect the derived JSONL again:

```bash
paic inspect redaction-review/conversation.redacted.jsonl
```

For a fixture containing only currently supported patterns, those supported body counts should be zero after redaction. Manual review still remains required.

## Relationship to deterministic checkpoints

`paic checkpoint` uses the same shared redaction primitive before selected excerpts are rendered. This prevents the explicit review command and checkpoint path from drifting into different secret-replacement rules.

Checkpoint redaction counts continue to describe only selected messages that can enter `CHECKPOINT.md`; the explicit redaction report describes the full derived conversation.
