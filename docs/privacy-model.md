# Privacy model

## 1. Runtime metadata

Web applications may embed account, session, bootstrap, telemetry, experimentation, and authorization structures next to visible conversation data. Those structures are not conversation history.

Adapters must prefer allowlisting conversation fields. The ChatGPT HTML adapter intentionally ignores `script#client-bootstrap` and only resolves the share conversation stream required to recover message content.

## 2. Conversation-body secrets

A user may intentionally or accidentally type credentials into a chat. That text *is* conversation content, so silently deleting it could change project history.

The canonical-history policy is therefore:

- detect supported suspicious secret patterns;
- report only category/count;
- never print the matched value;
- never silently rewrite canonical messages.

### Explicit derived redaction review

When the user explicitly wants a review copy, PAIC can produce **pattern-limited derived artifacts** without altering the source/canonical conversation:

```bash
paic redact conversation.clean.html -o redaction-review
```

The command writes:

```text
conversation.redacted.clean.html
conversation.redacted.compact.txt
conversation.redacted.jsonl
redaction-report.json
```

The transform uses the same redaction primitive as deterministic checkpoint generation. It covers the currently supported `BODY_PATTERNS` and replaces a recognized private-key block as a whole so the key material is not left behind after only masking its header.

Derived artifacts intentionally do not preserve the original title, source locator, or message metadata. The canonical input object/file is unchanged.

`redaction-report.json` is content-free by design. It binds the source and derived artifacts with conversation digests and records only structural evidence such as affected message index/role/source-message hash and counts by pattern. It does not include matched values, source paths/URLs, private titles, or message previews.

A successful supported-pattern rescan is **not** a general confidentiality guarantee. The report always states the equivalent of:

```text
supported_patterns_remaining = 0
manual_review_required = true
patterns_are_exhaustive = false
```

The first field means only that PAIC's currently supported secret-like regexes no longer match the derived body. It does not prove absence of arbitrary passwords, PII, proprietary text, credentials in unknown formats, or provider-specific secrets. Human review remains required before sharing.

Conversation digests provide deterministic provenance/integrity linkage between source and derived text. They are not an author signature or authenticity proof.

## 3. Compiler API boundary

If an external compiler backend is used, canonical conversation chunks are sent to that provider. Extraction, inspection, verification, `.aicb` creation, deterministic checkpoint generation, and pattern-limited redaction review do not require a model API.
