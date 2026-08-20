# Pre-v1 canonical role/text stream compatibility floor

Tracking issue: #83

Portable AI Context already has a narrow semantic stream that multiple alpha formats converge on:

```json
{"role":"user","text":"..."}
{"role":"assistant","text":"..."}
```

This document establishes a **pre-v1 regression floor** for those existing semantics. It does not declare a stable v1 canonical schema, add a schema-version identifier, or define the final long-term compatibility policy.

## Existing canonical facts

The current canonical message stream is:

- ordered;
- non-empty;
- role-limited to `user` and `assistant`;
- text-only at the canonical message level;
- contiguous when represented in the in-memory `Message.index` sequence;
- exported to standard JSONL as objects containing exactly `role` and `text`.

Runtime/source metadata, page/account/session state, provider-specific message IDs, tool traces, attachments, hidden reasoning, and source locators are not fields in this narrow standard JSONL stream.

These existing runtime facts live in:

```text
src/portable_ai_context/canonical_contract.py
```

with:

```python
CANONICAL_ROLE_ORDER = ("user", "assistant")
CANONICAL_ROLES = frozenset(CANONICAL_ROLE_ORDER)
CANONICAL_MESSAGE_FIELD_ORDER = ("role", "text")
CANONICAL_MESSAGE_FIELDS = frozenset(CANONICAL_MESSAGE_FIELD_ORDER)
```

The standard exporter, strict `.aicb` canonical-record validation, conformance harness, and tolerant generic JSONL importer all consume the shared role/field facts where applicable.

## Strict canonical output versus tolerant ingestion

The standard PAIC JSONL **output** contract is deliberately narrow: every emitted record has exactly the canonical field set and a canonical role.

The generic JSONL/NDJSON **input adapter** is a different boundary. It remains tolerant so simple external/local role-text streams can be ingested:

- unrelated non-object records can be ignored;
- unsupported roles such as `system` can be ignored;
- user/assistant objects may carry extra fields that are not imported into canonical content;
- empty supported-role text records can be ignored when other usable canonical records exist.

Centralizing the canonical role set must not silently convert that tolerant source adapter into the strict `.aicb` bundle validator.

This distinction lets PAIC accept simple external JSONL without widening what it itself claims as canonical exported state.

## Fixed historical specimen

The committed fixture is:

```text
tests/fixtures/canonical_role_text_golden.jsonl
```

It contains four fully synthetic user/assistant records and no provider/account/runtime metadata.

Pinned raw file SHA256:

```text
381db70fa84c54bb56d64847f695c2784dbfb2f8f3127bc4d9ed2ff620f63414
```

Pinned canonical conversation digest:

```text
a16d8e5671b80e1b5f771879dfc223c890883977087cd58c555bb47c5e8f64a4
```

Tests load the committed fixture directly through the normal adapter path. They do not invoke the current JSONL exporter to manufacture the historical input first.

This catches a class of regression that pure current-exporter → current-importer round trips cannot: both sides drifting together while an older role/text stream stops producing the same canonical conversation.

## What is pinned and what is not

The compatibility floor pins **semantics**, not incidental JSON formatting.

Pinned:

- ordered user/assistant role sequence;
- exact text values in the synthetic historical specimen;
- canonical conversation digest;
- standard output field set `{role,text}`;
- current canonical role set `{user,assistant}`;
- tolerant importer behavior described above.

Not declared stable here:

- whitespace around JSON tokens;
- JSON key ordering;
- whether a future stable format adds an explicit envelope/version outside the current JSONL stream;
- titles, source metadata, snapshot metadata, provider identifiers, or attachments as canonical JSONL fields;
- long-term multi-version migration policy.

A future exporter may change irrelevant formatting while preserving these semantics. Tests therefore parse current exporter records when checking the canonical field/role contract instead of requiring byte-for-byte equality with the golden file.

## Relationship to `.aicb`

The strict `.aicb` `0.1-alpha` reader requires each `conversation.jsonl` member record to contain exactly the shared canonical field set and a supported canonical role.

That strictness is part of the bundle integrity contract: extra fields inside a supposedly canonical bundle record cannot be silently ignored because doing so could allow signed/hashed/manifested bundle semantics to diverge from what PAIC actually imports.

This is intentionally stricter than generic `.jsonl` ingestion.

The separate `.aicb` historical compatibility floor is documented in:

```text
docs/aicb-compatibility.md
```

## Compatibility rules before v1

### 1. Do not silently widen the meaning of current canonical output

If the standard exporter starts emitting new canonical fields, roles, or non-text message semantics, treat that as an explicit contract decision with tests/docs/release notes. Do not let unrelated refactoring widen the stream accidentally.

### 2. Input tolerance is not canonical-schema expansion

Accepting an extra source-field on generic JSONL input does not make that field part of PAIC's canonical stream. Only explicitly normalized canonical state is exported.

### 3. Historical semantic identity must remain reviewable

Do not regenerate the golden fixture/hash merely to make a regression test pass. If a deliberate compatibility transition changes historical interpretation, document that transition explicitly and preserve enough evidence to explain the old behavior.

### 4. Security/privacy boundaries override convenience

A future compatibility argument is not sufficient reason to import runtime/session/auth/account data into canonical role/text metadata or to weaken strict `.aicb` validation.

### 5. Stable versioning remains a separate v1 decision

This issue deliberately does not invent `canonical-v1`, `1.0`, or another version marker. A stable versioning scheme should be chosen together with the final canonical schema, migration rules, and backward-compatibility policy rather than inferred from an alpha regression fixture.

## What CI proves

Normal CI must continue to prove:

- the committed historical JSONL file SHA is unchanged;
- loading it through the normal JSONL adapter preserves exact ordered messages;
- its canonical conversation digest is unchanged;
- it passes current canonical conformance;
- current standard JSONL output contains exactly the shared canonical field set and canonical roles;
- generic JSONL ingestion remains tolerant of extra fields/unrelated records as documented;
- strict `.aicb` validation and conformance use the shared canonical constants.

## Non-stability boundary

This work does **not** complete these Roadmap items:

```text
Stable canonical schema
Backward-compatibility policy
```

Before those can be checked, PAIC still needs an intentional stable-schema/versioning decision covering additive changes, unsupported/new roles or modalities, migration/deprecation rules, compatibility duration, and cross-implementation expectations.

The historical role/text specimen gives that future policy a concrete semantic floor; it is not the policy itself.
