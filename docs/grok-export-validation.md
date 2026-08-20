# Grok consumer export discovery and validation

Tracking issue: #66

PAIC does **not** currently claim a Grok consumer-chat adapter. This document defines the evidence gate that must be completed before one can be added.

## First-party source boundary

xAI's Consumer FAQ states that individual Grok users can access, download, and delete their data from the Grok mobile app or Grok.com through **Settings / Data Controls**. xAI's CCPA transparency report separately identifies completed **xAI Account Data Downloads via xAI Data Controls**.

Primary references:

- https://x.ai/legal/faq
- https://x.ai/legal/ccpa

Those public documents establish that a first-party account-data download exists. They do **not** document a stable conversation archive filename, JSON field set, or thread/message schema that PAIC can safely assume.

The separate Grok Build coding-agent CLI is not this source contract. Its documented command:

```text
grok export <session-id> [output]
```

exports a Grok Build session transcript as Markdown. That is a local coding-agent session format, not evidence of the Grok.com consumer account-data-download shape.

Primary reference:

- https://docs.x.ai/build/cli/reference

## Deliberately non-sensitive sentinel conversation

Before requesting a real account download, create a brand-new ordinary Grok consumer chat containing no private/account/project information.

Send exactly:

```text
PAIC_GROK_EXPORT_SENTINEL_20260819_USER. Reply exactly with the same marker, replacing the final word USER with ASSISTANT.
```

The intended assistant marker is:

```text
PAIC_GROK_EXPORT_SENTINEL_20260819_ASSISTANT
```

Do not use attachments, images, private files, connectors, or unrelated account history as the test subject.

## Raw export privacy boundary

The xAI account download can contain personal/account data. Keep the original ZIP/files on the tester's own computer.

Never commit, attach, or paste the raw export into GitHub, an issue, a chat, or a PAIC fixture. In particular, do not publish:

- normal Grok conversation text;
- name/email/account identity;
- account, conversation, message, or attachment identifiers;
- private URLs or query strings;
- timestamps considered sensitive;
- cookies, auth/session material, API keys, or tokens;
- attachment/file contents;
- private local filesystem paths.

The discovery probe is intended to produce a **derived structural specimen** that can be manually reviewed before any sharing.

## Unknown-schema probe

Run:

### Windows PowerShell

```powershell
py -3 tools\grok_export_probe.py "C:\path\to\your\xai-download.zip" -o paic-grok-export.sanitized.json
```

If `py -3` is unavailable but `python` is Python 3.10+, use `python` instead.

### macOS / Linux

```bash
python3 tools/grok_export_probe.py "/path/to/your/xai-download.zip" \
  -o paic-grok-export.sanitized.json
```

The source may also be an extracted directory, `.json`, `.jsonl`, or `.ndjson` file.

The probe deliberately does **not** look for provider keys such as `messages`, `conversation`, `role`, `content`, or guessed xAI filenames. Instead it:

1. scans bounded JSON / JSONL / NDJSON input locally;
2. counts HTML documents but does not use HTML body text as public evidence;
3. searches arbitrary JSON structure for the fixed user and assistant sentinel strings;
4. chooses the minimal dictionary context whose subtree contains both markers;
5. requires exactly one such minimal dictionary context;
6. sanitizes every ordinary string and number;
7. preserves only structural field names, a tiny role/type-like public literal allowlist, booleans/null, and the two fixed sentinels;
8. redacts suspicious map keys that look like emails, URLs, UUIDs, long opaque IDs, hashes, or token-like values;
9. refuses oversized/deep/node-heavy inputs and oversized sanitized specimens rather than silently truncating them;
10. reports only content-free counts, a specimen hash/size, and the output **basename**.

The tool makes no network calls and does not copy the raw export into the repository.

## Resource limits

Defaults are intentionally finite:

```text
per JSON/JSONL member/file: 256 MiB
total JSON/JSONL bytes read: 512 MiB
parsed documents/records: 512
ZIP members: 10,000
JSON structure nodes scanned: 500,000
JSON nesting depth: 128
sanitized specimen: 1,024 KiB
```

If a legitimate first-party export exceeds one of these limits, increase only the relevant CLI limit explicitly after confirming the file is expected. A limit failure is preferable to silent truncation or uncontrolled memory use.

Available controls:

```text
--max-json-mb
--max-total-json-mb
--max-documents
--max-zip-members
--max-nodes
--max-depth
--max-specimen-kb
```

## Expected report shape

A successful run prints content-free JSON similar to:

```json
{
  "assistant_marker_occurrences_in_context": 1,
  "html_documents_seen": 0,
  "json_files_seen": 1,
  "json_structure_nodes_scanned": 123,
  "jsonl_ndjson_files_seen": 0,
  "matched_minimal_contexts": 1,
  "ok": true,
  "output_file": "paic-grok-export.sanitized.json",
  "parsed_documents_scanned": 1,
  "provider": "grok",
  "raw_export_not_copied": true,
  "sanitized_specimen_bytes": 2048,
  "sanitized_specimen_sha256": "...",
  "schema_fields_assumed": false,
  "user_marker_occurrences_in_context": 1
}
```

Counts can differ across real exports. The output does not claim that a particular xAI schema is supported.

If the export contains only HTML or no JSON structure containing both markers, keep the raw export local and report only the content-free failure. Do not manually trim raw provider data to force a match.

## Human review before sharing

Open `paic-grok-export.sanitized.json` locally and review the entire derived specimen.

It may contain:

- ordinary structural field names;
- list/dictionary shape;
- safe role/type-like literals such as `user`, `assistant`, `human`, `model`, `system`, or `text`;
- the two fixed sentinel markers;
- `<redacted:...>` and `<redacted-key-N>` placeholders.

Do **not** share the specimen if any real private value remains. If sanitization appears insufficient, report only that the sanitizer needs hardening; do not paste the leaked value.

## What happens after real evidence

A Grok adapter may be implemented only after a deliberately non-sensitive first-party download establishes a stable recoverable structure.

The implementation sequence is:

```text
real first-party account download kept local
→ bounded unknown-schema probe
→ human-reviewed sanitized structural evidence
→ narrow parser for only the evidenced shape
→ synthetic regression fixture with fake values
→ second real sentinel validation
→ paic inspect / conform
→ normal 10-job CI
```

A synthetic fixture must be derived from the structural contract, not copied from private provider data.

If the first-party download does not expose usable ordered conversation text, document that limitation before considering a browser-DOM capture route.

## Evidence boundary

The probe and its unit tests prove only that PAIC has a bounded, privacy-oriented **discovery tool**. They do not prove:

- the real xAI archive uses JSON/JSONL/NDJSON;
- the real archive contains Grok conversations;
- any guessed field name or filename;
- ordered user/assistant reconstruction;
- attachment fidelity;
- Grok adapter support.

Those claims require deliberately non-sensitive real first-party evidence under #66.
