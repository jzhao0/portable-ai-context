# Grok first-party account-download validation

Tracking issue: #66

Portable AI Context does not currently claim a Grok consumer-chat adapter. xAI documents a first-party data-download control, but it does not publish the downloaded archive's conversation file names or a stable JSON schema that PAIC can safely target.

The first validation therefore uses a deliberately non-sensitive **unknown-schema structural probe**. The raw account download must remain on the tester's own computer.

## First-party route

xAI's current Consumer FAQ says users can access, download, and delete their data from:

```text
Grok mobile app or Grok.com
→ Settings
→ Data Controls
→ download your data
```

Official xAI references:

- https://x.ai/legal/faq
- https://x.ai/legal/ccpa

The xAI CCPA transparency report separately records completed **xAI Account Data Downloads via xAI Data Controls**, so this is a first-party user-data workflow rather than a third-party exporter.

Do not confuse it with the separate Grok Build CLI command `grok export <session-id>`, which xAI documents as exporting local coding-agent sessions as Markdown. That is not evidence of the Grok.com consumer-chat account-download format.

## 1. Create a disposable Grok conversation

Create a brand-new Grok.com conversation containing no personal information, private project content, uploaded files, connectors, or other account-specific material.

Send exactly:

```text
PAIC_GROK_EXPORT_SENTINEL_20260819_USER. Reply exactly with the same marker, replacing the final word USER with ASSISTANT.
```

The desired assistant reply is exactly:

```text
PAIC_GROK_EXPORT_SENTINEL_20260819_ASSISTANT
```

If Grok adds extra text, do not edit the conversation. The structural probe remains useful as long as each fixed sentinel occurs exactly once in the downloaded structured data.

## 2. Request the xAI account download

Use the first-party Grok **Settings / Data Controls** download flow documented by xAI.

The resulting archive can contain account data beyond the disposable test conversation. Treat the entire raw download as sensitive.

**Never upload or paste the original xAI ZIP, JSON/JSONL files, account metadata, or normal Grok history into GitHub or ChatGPT.**

Download it only to your own computer and run the probe locally.

## 3. Run the unknown-schema structural probe

The probe makes no assumptions about xAI field names such as `messages`, `conversation`, `role`, or `content`.

It scans local JSON, JSONL, and NDJSON documents for the two fixed sentinels. It first finds the deepest/minimal JSON object or array whose subtree contains both markers. If that minimal container is an array stored directly under an object key, the probe deliberately preserves exactly one parent object so the sanitized specimen retains the field label for that ordered array. A dict candidate is not expanded because it already exposes its own field names; a root array remains an array.

This one-level field context makes the specimen more useful for discovering a real schema without broadening it to unrelated account-level data. The resulting context is still subject to the same strict structural node limit and value redaction.

### Windows PowerShell

From a current repository checkout:

```powershell
py -3 tools\grok_export_shape_probe.py "C:\path\to\your\xai-download.zip" -o paic-grok-export-shape.sanitized.json
```

If `py -3` is unavailable but `python` is Python 3.10+, use `python`.

### macOS / Linux

```bash
python3 tools/grok_export_shape_probe.py "/path/to/your/xai-download.zip" \
  -o paic-grok-export-shape.sanitized.json
```

An extracted directory or a `.json`, `.jsonl`, or `.ndjson` file can also be passed as the source.

## Probe safety contract

The probe:

- keeps raw provider bytes local;
- never copies the raw archive into the repository;
- never prints source/member filenames or local paths in its success report;
- counts HTML files but does not scrape their contents into the specimen;
- preserves only JSON object/array structure, safe dictionary keys, a tiny public literal set, and the two fixed sentinels;
- redacts all ordinary string values;
- redacts all numbers;
- redacts suspicious dictionary keys that look like URLs, email-like strings, timestamps, numeric IDs, UUIDs, long hex values, or opaque tokens;
- requires each sentinel to occur exactly once;
- refuses multiple ambiguous contexts;
- refuses an oversized structural context instead of silently truncating it;
- reports `schema_claimed: false` because this is discovery evidence, not a parser contract.

The probe supports explicit limits:

```text
--max-document-mb 256
--max-specimen-nodes 5000
```

Increase them only after understanding why the real account download requires it. Do not manually cut private provider files into smaller fragments merely to make the probe succeed.

## Expected success report

Exact counts/hash/size depend on the current xAI export, but stdout has this shape:

```json
{
  "ok": true,
  "provider": "grok",
  "probe_mode": "unknown_schema_minimal_common_context_v1",
  "json_documents_scanned": 1,
  "jsonl_records_scanned": 0,
  "html_documents_seen": 0,
  "other_files_seen": 0,
  "user_sentinel_occurrences": 1,
  "assistant_sentinel_occurrences": 1,
  "minimal_context_type": "object",
  "minimal_context_nodes": 20,
  "sanitized_specimen_sha256": "...",
  "sanitized_specimen_bytes": 800,
  "output_file": "paic-grok-export-shape.sanitized.json",
  "schema_claimed": false,
  "raw_export_not_copied": true
}
```

If there is no readable JSON/JSONL, the tool reports only content-free file-type counts. If a sentinel is duplicated or no unique common context exists, it reports counts rather than provider data.

## 4. Human-review the sanitized specimen

Open only:

```text
paic-grok-export-shape.sanitized.json
```

Expected safe material:

- JSON field names / object/list structure;
- public role/type literals such as `user`, `assistant`, `text`, `message`, `content`, or `Grok` when present;
- the two fixed PAIC sentinel markers;
- `<redacted:...>` placeholders;
- booleans/null values.

Do **not** share the specimen if it contains any real:

- normal Grok conversation text;
- name or email address;
- xAI/X account/user ID;
- conversation/message UUID or opaque ID;
- private URL or query string;
- timestamp you consider sensitive;
- cookie, token, auth/session value;
- connector data;
- attachment/file name or content;
- local filesystem path.

If anything private remains, stop and report only that the sanitizer needs hardening. Do not paste the private value itself.

## 5. What happens after one safe real specimen

A real human-reviewed structural specimen is evidence for designing a parser; it is not itself the parser.

If the xAI Account Data Download exposes a sufficiently stable conversation structure, #66 proceeds with:

1. documenting the exact real-derived structural subset;
2. creating a fully synthetic regression fixture with fake IDs/text/timestamps;
3. implementing only that evidenced Grok source shape;
4. validating message order and the two fixed sentinel markers;
5. running `paic inspect` and `paic conform`;
6. repeating one deliberately non-sensitive real-export smoke against the finished adapter;
7. normal 10-job CI.

If the first-party download contains only unusable HTML/binary/account metadata or cannot recover conversation order, record that limitation content-free before considering a dedicated Grok Web DOM capture profile.

## Evidence boundary

Until the real account-download probe succeeds and a parser is implemented, README/release language must continue to treat Grok as **unsupported / roadmap-only**.
