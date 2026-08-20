# Pre-v1 `.aicb` compatibility floor

Tracking issue: #79

Portable AI Context has published an alpha `.aicb` contract identified as:

```text
0.1-alpha
```

This document defines a **pre-v1 regression floor** for that published contract. It does not declare the canonical schema or `.aicb` format stable, and it does not define the final long-term v1 support window.

## Why this floor exists

A round-trip test that writes a bundle with the current writer and immediately loads it with the current reader cannot detect every compatibility regression. Writer and reader can drift together while an older already-created bundle stops loading.

PAIC therefore keeps a fixed synthetic `0.1-alpha` golden specimen that is independent of the current writer at test time.

The committed fixture is:

```text
tests/fixtures/aicb_0_1_alpha_golden.aicb.b64
```

It is base64 text only so the repository can keep the fixed historical ZIP bytes in a reviewable/versioned file even where binary-file write tooling is inconvenient. Tests decode the committed bytes and feed the resulting `.aicb` file directly to the normal adapter registry/reader. They do **not** call `write_bundle()` to regenerate the historical specimen before loading it.

Pinned decoded SHA256:

```text
3db7230deb0c3b665380895d9acbed044e494282595039fb75e1d751bb4e099e
```

Pinned canonical conversation digest:

```text
fbe519c91e833b034a7dae92e0802afc86b29bf3670beb365cf8e8a1d4e3aa85
```

The specimen contains only deliberately synthetic text and a synthetic source kind. It contains no real account identifier, provider URL, local path, token, credential, or private conversation material.

## Runtime contract source of truth

Current runtime bundle constants live in:

```text
src/portable_ai_context/bundle_contract.py
```

The current contract exports:

```python
AICB_SCHEMA_VERSION = "0.1-alpha"
AICB_MEMBER_ORDER = (
    "manifest.json",
    "conversation.jsonl",
    "integrity.json",
    "privacy.json",
)
AICB_REQUIRED_MEMBERS = frozenset(AICB_MEMBER_ORDER)
```

Both the bundle writer and strict bundle reader consume those runtime constants.

`schemas/conversation-bundle.schema.json` remains a static JSON Schema artifact rather than importing Python code. CI therefore verifies that its schema-version constant, artifact enum, and artifact cardinality match the runtime contract.

## Compatibility rules before v1

### 1. A published version identifier keeps its meaning

Do not change the semantic meaning of `0.1-alpha` while continuing to label new bytes as `0.1-alpha`.

If a future bundle contract is intentionally incompatible, give it a new explicit schema version. Do not silently reinterpret the old identifier.

### 2. Reader support and writer output are separate decisions

A future writer may eventually emit a newer bundle version. That does not automatically permit the reader to forget the already-published `0.1-alpha` contract.

Reader support for an older version should be removed only through an explicit compatibility-policy decision with migration/release notes, not as an incidental side effect of refactoring the current writer.

### 3. Unknown versions fail closed

The current strict reader rejects a manifest that declares an unsupported schema version. It does not guess that an unknown future version is “close enough” to `0.1-alpha`.

A future multi-version reader should add explicit dispatch/validation for each supported version rather than weakening the existing version check into heuristic acceptance.

### 4. The committed golden specimen is a floor, not the entire format specification

Passing the golden test proves that one fixed historical bundle remains readable and preserves its canonical conversation identity. It does not prove compatibility with every possible bundle ever emitted under an experimental alpha contract.

The full strict reader tests remain responsible for archive traversal, duplicate members, symlink-like entries, compression/size limits, JSON/JSONL shape, integrity consistency, privacy consistency, and unsupported-version failure.

### 5. Security validation is not relaxed for compatibility

Backward readability is not a reason to accept unsafe ZIP members, malformed canonical records, stale integrity metadata, or mismatched privacy reports.

If an old artifact is structurally unsafe under a necessary security hardening, security takes precedence. Any deliberate compatibility break must be documented explicitly rather than hidden behind permissive parsing.

## Golden-specimen change policy

The fixture hash is intentionally pinned. A normal writer refactor must not regenerate or replace it.

Changing the fixture is allowed only when the change itself is the subject of explicit review, for example:

- correcting evidence that the fixture never represented a valid published contract;
- removing accidentally committed sensitive material;
- adding an additional historical specimen while preserving the original one;
- a documented compatibility-policy transition.

Do not update the pinned hash merely to make a failing compatibility test green.

## What must remain green

Normal CI must continue to prove:

- the fixed `0.1-alpha` specimen's decoded SHA256 is unchanged;
- the normal registry/reader loads it without using the current writer;
- title and user/assistant messages match exactly;
- the canonical conversation digest matches exactly;
- bundle schema version and original source kind metadata are preserved;
- bundle integrity verification remains true;
- JSON Schema version/member declarations match runtime constants;
- current writer output uses the shared runtime contract;
- unknown bundle versions still fail closed through the existing strict reader suite.

## Non-stability boundary

This floor does **not** check any v1 Roadmap item complete.

The following remain separate future decisions:

```text
Stable canonical schema
Stable .aicb bundle format
Backward-compatibility policy
```

Before v1, PAIC still needs to define such questions as:

- which historical pre-v1 versions a stable reader must support and for how long;
- whether migrations are required between bundle generations;
- additive-extension rules for manifests and canonical records;
- version-negotiation/feature-declaration rules;
- deprecation timing and release-note requirements;
- compatibility guarantees for libraries other than the Python reference implementation.

The `0.1-alpha` golden specimen gives those future decisions a concrete historical artifact they cannot accidentally erase.
