# Published-alpha compatibility baseline

Tracking issue: #71

Portable AI Context has a public `0.1.0a2` alpha release. That release introduced a real external artifact contract through `.aicb` schema version:

```text
0.1-alpha
```

This document defines a deliberately narrow compatibility baseline for that **published alpha**. It does not declare the overall PAIC API, canonical model, or bundle format stable for v1.0.

## Baseline release

The compatibility reference is:

```text
release tag: v0.1.0a2
release commit: 5938f2c52e7ce015662b2c20feb4c5c2d76e179f
bundle schema: 0.1-alpha
```

A repository comparison performed when this baseline was introduced showed that the `.aicb` reader/writer and bundle schema had not changed between that published tag and the then-current main branch.

## Read-compatibility rule

Starting with this baseline:

> Current and future PAIC main should continue to read valid `0.1-alpha` bundles that conform to the published `v0.1.0a2` contract.

If a future bundle format needs incompatible semantics, it should use a **new `schema_version`** rather than silently changing what `0.1-alpha` means.

The current reader remains intentionally strict about the archive member set, canonical JSONL records, integrity agreement, privacy-report shape, resource limits, and supported schema version.

A security-critical flaw in an old format may justify intentionally withdrawing support. Such a break must be explicit, documented, reviewed, and covered by tests; it must not happen accidentally as a side effect of unrelated refactoring.

## Historical fixture strategy

The repository contains fixed synthetic member payloads under:

```text
tests/fixtures/compat/v0.1.0a2-aicb/
```

They represent the external member payload contract of a valid `0.1-alpha` bundle:

```text
manifest.json
conversation.jsonl
integrity.json
privacy.json
```

The fixture is deliberately non-sensitive:

- fixed synthetic title and source kind;
- fixed timestamp;
- four fixed user/assistant messages;
- fixed integrity hashes/digest;
- zero supported body-secret counts;
- no account identity, private URL, auth material, or local machine path.

The compatibility test locks SHA256 for every member file. `.gitattributes` forces LF checkout for only this fixture directory so the historical bytes remain identical on Windows, macOS, and Linux.

Critically, the read-compatibility test **does not call the current bundle writer to create those member payloads**. It ZIPs the fixed historical bytes at test time and feeds the result directly to the current reader. That prevents writer and reader from drifting together while still making a self-generated round trip look green.

The current writer is tested separately for semantic compatibility with the same published `0.1-alpha` contract.

## What this baseline guarantees

For a valid bundle matching the published `0.1-alpha` contract, the guard requires current PAIC to preserve:

- successful `.aicb` registry loading;
- active source kind `aicb`;
- recorded original source-kind provenance;
- exact canonical user/assistant role/text/order;
- title;
- canonical conversation digest;
- integrity verification;
- normal `paic inspect`, `paic verify`, and `paic conform` behavior.

The current writer is also required to keep emitting, while it still declares `0.1-alpha`:

- exactly the four required root archive members;
- `schema_version = 0.1-alpha`;
- required manifest conversation metadata including `source_kind`;
- canonical JSONL records containing only `role` and `text`.

ZIP bytes are **not** required to be reproducible because creation timestamps and ZIP metadata are not the portable semantic contract.

## JSON Schema alignment

`schemas/conversation-bundle.schema.json` describes the manifest portion of the current runtime contract.

The schema is aligned with constraints the existing reader already enforces, including:

- `schema_version = 0.1-alpha`;
- non-empty `created_at`;
- required `title`, `message_count`, `digest`, and `source_kind`;
- lowercase 64-hex SHA256 digest shape;
- current source-kind identifier grammar;
- exactly four unique artifact names from the published member set.

The runtime reader currently tolerates additional manifest/conversation metadata fields while validating the fields it consumes. The JSON Schema therefore keeps `additionalProperties: true` in those locations rather than claiming a stricter contract than the implementation actually provides.

The archive reader itself remains stricter about ZIP members: unknown extra archive members are rejected.

## What this baseline does **not** guarantee

This guard does not declare any of the following stable:

- the internal Python `Conversation`, `Message`, `SourceInfo`, or `SnapshotInfo` dataclass APIs;
- every adapter/provider export shape;
- clean HTML or compact TXT remaining unchanged forever;
- every pre-release `.aicb` artifact created before the published `0.1.0a2` baseline;
- future writers continuing to emit `0.1-alpha` indefinitely;
- automatic migration between hypothetical future bundle schema versions;
- v1 semantic-versioning/backward-compatibility policy;
- digital signatures, publisher authenticity, or proof of origin.

The v1.0 roadmap items **Stable canonical schema**, **Stable `.aicb` bundle format**, and **Backward-compatibility policy** therefore remain unchecked.

## Relationship to v1 work

This baseline is a prerequisite/guardrail for future stability work, not its completion.

A future v1 effort still needs to decide and document, among other things:

- which public Python/API surfaces are stable;
- how new bundle schema versions negotiate compatibility;
- whether/when old writers are supported;
- semantic-versioning rules for canonical and bundle changes;
- formal migration tooling between schema generations;
- signature/authenticity policy.

Until then, the project can evolve while preventing accidental loss of access to the first published `.aicb` contract.
