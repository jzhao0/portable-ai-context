# Adapter conformance contract

Portable AI Context normalizes provider-specific inputs into one alpha canonical `Conversation`. Adapter-specific parser tests are still necessary, but every adapter should also pass the same shared post-canonicalization contract.

The shared runner lives in:

```text
portable_ai_context.conformance.inspect_conformance
```

The content-free CLI entry point is:

```bash
paic conform <source>
```

## Why this exists

A parser can appear to work while still violating portability invariants: it can emit a noncanonical role, skip/reuse message indices, preserve empty messages, leak runtime/account values into canonical metadata, or produce text that cannot survive the project's own standard export formats.

The conformance layer tests those cross-adapter invariants once, independently of provider-specific schema logic.

It does **not** prove that a provider parser extracted every semantically correct message from a real export. Source-specific expected-message fixtures and real-source validation remain separate evidence layers.

## Core canonical checks

`inspect_conformance(conversation)` checks:

- the canonical message stream is non-empty;
- `source.kind` is present;
- every role is in the current alpha canonical set: `user` or `assistant`;
- message indices are exactly `0..N-1`;
- every message has non-empty string text;
- integrity message/user/assistant counts agree with the canonical stream;
- a deterministic conversation digest is available;
- clean HTML export → reload preserves the canonical digest;
- compact TXT export → reload preserves the canonical digest;
- JSONL export → reload preserves the canonical digest.

Round-trip equality is digest-based. The integrity digest hashes canonical role + normalized text, so title/provenance differences between export formats do not create false failures.

## Source-specific test assertions

Adapter tests can add two optional evidence layers.

### Expected role/text sequence

```python
report = inspect_conformance(
    conversation,
    expected_messages=[
        ("user", "Synthetic question"),
        ("assistant", "Synthetic answer"),
    ],
)
```

Expected text is compared after the same newline normalization used by integrity hashing. This catches a parser that produces a structurally valid conversation but silently extracts the wrong synthetic messages.

### Forbidden runtime/private values

Synthetic fixtures should deliberately include fake runtime/account values outside the supported conversation text fields. Pass those fake values as `forbidden_values`:

```python
report = inspect_conformance(
    conversation,
    forbidden_values=[
        "PRIVATE_FAKE_ACCOUNT_ID",
        "PRIVATE_FAKE_SESSION_TOKEN",
    ],
)
```

The check searches canonical title, message text/metadata, conversation metadata, source metadata, and snapshot metadata. It intentionally excludes `source.locator` and `source.fingerprint`: the locator is local provenance rather than normalized conversation content, and the fingerprint is derived data.

Failure reports never echo the forbidden value.

## Content-free report

A successful CLI report resembles:

```json
{
  "ok": true,
  "source_kind": "jsonl",
  "message_count": 2,
  "conversation_digest": "...",
  "checks": {
    "message_stream_nonempty": true,
    "source_kind_present": true,
    "canonical_roles": true,
    "contiguous_indices": true,
    "nonempty_text": true,
    "integrity_consistent": true,
    "roundtrip_clean_html": true,
    "roundtrip_compact_txt": true,
    "roundtrip_jsonl": true
  },
  "violations": []
}
```

The CLI intentionally omits:

- conversation title;
- message text or tail text;
- local source locator/path;
- source fingerprint;
- raw provider metadata;
- forbidden values.

If the source loads but violates the shared contract, `paic conform` prints the content-free report and exits with status `3`. Source parsing/recognition errors continue to use the normal PAIC error path.

## Violation semantics

Violation records contain only stable codes and generic messages. Current codes include:

```text
empty_message_stream
missing_source_kind
noncanonical_role
noncontiguous_indices
empty_message_text
integrity_mismatch
expected_messages_mismatch
forbidden_value_present
roundtrip_clean_html_mismatch
roundtrip_compact_txt_mismatch
roundtrip_jsonl_mismatch
```

Do not add raw parser exception text, message text, private values, source paths, or provider response bodies to conformance violations.

## Evidence layers

Keep these evidence classes distinct:

1. **Adapter-specific synthetic fixture** — proves the parser handles a known artificial shape and expected messages.
2. **Shared conformance harness** — proves the resulting canonical conversation satisfies cross-adapter invariants and survives standard round trips.
3. **Cross-platform CI** — proves deterministic behavior on the supported OS/Python matrix.
4. **Real deliberately non-sensitive provider validation** — proves a current provider export/page actually matches the claimed source shape.

Passing layers 1–3 does not authorize describing an adapter as real-provider validated. Claude/Gemini real-export evidence remains tracked separately in Issue #17.

## Adding a future adapter

For a new source adapter:

1. add a deliberately synthetic source fixture containing an unambiguous user/assistant sequence;
2. add fake runtime/account/tool/attachment values outside the supported text fields;
3. load the fixture through the normal registry whenever possible;
4. call `inspect_conformance` with `expected_messages` and `forbidden_values`;
5. require `report.ok` and all checks to pass on the full CI matrix;
6. add source-specific negative/malformed cases;
7. obtain deliberately non-sensitive real-source evidence separately before upgrading compatibility claims.

The shared harness is an alpha contract and may evolve before the canonical schema is stabilized for 1.0.