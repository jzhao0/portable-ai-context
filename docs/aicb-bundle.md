# `.aicb` alpha bundle import and trust model

Portable AI Context uses `.aicb` as a ZIP-based handoff container. The current schema version is:

```text
0.1-alpha
```

This is a **pre-1.0 unstable format**. The member set, manifest shape, limits, and compatibility policy may change before 1.0.

## Bidirectional alpha flow

A bundle can be created and then reopened through the normal PAIC source registry:

```bash
paic bundle conversation.clean.html -o project.aicb
paic inspect project.aicb
paic verify project.aicb
paic conform project.aicb
paic checkpoint project.aicb -o checkpoint
```

No special CLI import command is required. A validated bundle becomes a canonical `Conversation` with active source kind:

```text
aicb
```

The manifest's recorded original source kind is retained only as validated provenance metadata. It does not replace the active `aicb` source kind.

## Current strict member contract

An alpha bundle must contain exactly these four root-level members:

```text
manifest.json
conversation.jsonl
integrity.json
privacy.json
```

The reader rejects:

- missing members;
- extra/unknown members;
- duplicate member names;
- nested member paths;
- `..` traversal paths;
- backslash-style paths;
- absolute/drive-prefixed paths;
- directory entries;
- symlink-like ZIP entries;
- encrypted members;
- unsupported compression methods;
- archives or members beyond the documented alpha resource limits.

Members are read in memory. The reader does not extract archive paths to the filesystem.

## Resource limits

The current alpha reader applies explicit caps before trusting ZIP payloads:

```text
compressed archive size:       128 MiB
single uncompressed member:     96 MiB
total uncompressed member size: 128 MiB
ZIP member count metadata cap:   8
```

The strict member-set contract still requires exactly four accepted members. The larger metadata count cap is a pre-validation resource guard.

These values are alpha implementation limits, not a permanent portability guarantee.

## Canonical integrity verification

`conversation.jsonl` is treated as the canonical role/text payload. Under the current bundle contract, every non-empty JSONL line must be exactly a canonical record with:

```json
{"role": "user|assistant", "text": "..."}
```

Unknown fields are rejected rather than silently ignored inside `.aicb`, even though the generic standalone JSONL adapter is intentionally more permissive.

After parsing, PAIC recomputes canonical integrity from the recovered messages. It compares the recomputed result against:

- manifest `message_count`;
- manifest conversation `digest`;
- `integrity.json` message/user/assistant counts;
- `integrity.json` conversation digest;
- first-message hash;
- last-message hash;
- last-user hash;
- last-assistant hash.

A mismatch fails closed. PAIC does not silently repair the archive.

The recovered canonical message order and role/text digest must remain identical across:

```text
source -> .aicb -> load .aicb
```

The loaded conversation must also satisfy the shared clean HTML / compact TXT / JSONL conformance round trips.

## Privacy report handling

`privacy.json` is not blindly trusted.

PAIC recomputes the supported body-secret pattern counts from recovered canonical messages and requires them to agree with the recorded `body_secret_counts` and `safe_to_share_automatically` flag.

Recorded runtime-marker counts are different: they originated from the source adapter before bundling and cannot be reconstructed from canonical JSONL. The `.aicb` reader validates only that they are a string-to-nonnegative-integer count mapping, then discards them rather than importing provider-controlled keys into current canonical metadata.

The bundle reader does **not** turn privacy inspection into a general confidentiality scrubber. Conversation body text remains canonical user content.

## Provenance semantics

A loaded bundle uses:

```text
source.kind = aicb
```

Safe metadata currently records:

```text
bundle_schema_version
bundle_original_source_kind
bundle_integrity_verified
```

`bundle_original_source_kind` must match the same safe identifier grammar used by PAIC source kinds. An arbitrary manifest value is not allowed to become the active source type.

The creating machine's original source locator/path is not required for import and is not stored by the current bundle writer. The loaded `SourceInfo.locator` refers only to the `.aicb` file being opened on the current machine.

## Integrity is not authenticity

The current SHA256 hashes provide **internal consistency and tamper visibility for canonical message content**. They do not prove:

- who created the bundle;
- who authored the conversation;
- that the bundle came from a particular provider account;
- that manifest metadata was signed;
- that a malicious party could not create a new self-consistent bundle.

There is no bundle signature or trusted-author identity layer in `0.1-alpha`.

In particular, metadata that is not derivable from canonical role/text content—such as the manifest title, recorded creation timestamp, and recorded original source kind—can be validated for shape/safety but cannot be cryptographically authenticated by the current internal digest alone.

Do not describe `.aicb` SHA256 verification as a digital signature or proof of origin.

## Failure behavior

Bundle parsing errors use concise contract-level messages. They do not intentionally include embedded conversation text, secret values, or archive member contents.

Examples of failure categories include:

```text
AICB bundle contract violation: archive is missing a required member
AICB bundle contract violation: manifest digest does not match canonical conversation
AICB bundle contract violation: integrity.json canonical field mismatch: last_user_hash
```

## Compatibility policy for the alpha

The current reader is deliberately strict:

- supported schema: exactly `0.1-alpha`;
- unknown archive members: rejected;
- unsupported future schema versions: rejected;
- malformed/tampered bundles: rejected rather than repaired.

A backward-compatibility policy and stable `.aicb` format remain v1.0 work.