# Privacy-safe real export validation

Issue #17 validates Claude and Gemini adapters against deliberately non-sensitive real provider exports without moving a user's full account archive into GitHub, CI, or a chat.

## Core rule

**Never upload the raw provider export for this validation.**

The workflow is:

1. create one new standalone provider conversation containing a unique, deliberately public PAIC sentinel;
2. request the provider's official export;
3. keep the raw archive local;
4. run `tools/real_export_probe.py` locally;
5. share only the generated sanitized specimen and the probe's content-free report;
6. use that specimen to verify/fix the adapter, then convert any observed structural variant into a synthetic regression fixture.

The probe preserves JSON keys, list/dict structure, a small set of parser-relevant public literals, and the PAIC sentinel. Other string values, identifiers, timestamps, URLs, account metadata, and numbers are replaced with placeholders. Strings containing the sentinel are reduced to the sentinel itself, except the parser-relevant Gemini `Prompted ` / `Prompted: ` prefix.

The probe hard-fails when more than one provider record contains the sentinel; it does not guess which record to expose.

## Claude validation

Create a new standalone Claude conversation containing no personal/private material. Send:

```text
PAIC_CLAUDE_REAL_EXPORT_SENTINEL_20260819. Reply exactly: PAIC_CLAUDE_REAL_EXPORT_SENTINEL_20260819_OK
```

Verify the reply is exactly the requested marker before requesting the export.

Anthropic's current official export path for individual users is **Settings → Privacy → Export data** in the Claude web or desktop app. Anthropic states that the export includes conversation data and user data for the account, which is why the raw archive must remain local.

Official reference:
https://support.anthropic.com/en/articles/9450526-how-can-i-export-my-claude-data

After downloading the archive, run from a current Portable AI Context checkout:

```bash
python tools/real_export_probe.py claude /path/to/claude-export.zip \
  --sentinel PAIC_CLAUDE_REAL_EXPORT_SENTINEL_20260819 \
  -o paic-claude-real.sanitized.json
```

Share only:

- the JSON report printed by the probe; and
- `paic-claude-real.sanitized.json` after a quick human inspection confirms it contains no private values.

Do not share the original ZIP or other extracted files.

## Gemini validation

Create a new standalone Gemini conversation containing no personal/private material. Send:

```text
PAIC_GEMINI_REAL_EXPORT_SENTINEL_20260819. Reply exactly: PAIC_GEMINI_REAL_EXPORT_SENTINEL_20260819_OK
```

Verify the reply before requesting the archive.

Google's current official path for Gemini chat activity is Google Takeout:

1. **Deselect all** products.
2. Select **My Activity**.
3. Open **All activity data included**.
4. Deselect all activity products inside that dialog.
5. Select **Gemini Apps**.
6. Continue to create a one-time archive.

The standalone **Gemini** Takeout product is for other Gemini data such as Gems; Gemini Apps Activity is selected through **My Activity** for chat/activity validation.

Official references:
https://support.google.com/gemini/answer/16920332
https://support.google.com/accounts/answer/3024190

If Takeout offers a format selector for My Activity, choose JSON for this adapter validation. If the resulting archive contains only HTML for the selected activity, do not paste the HTML: the probe will stop with a content-free message reporting that no readable JSON document was found.

Run:

```bash
python tools/real_export_probe.py gemini /path/to/takeout.zip \
  --sentinel PAIC_GEMINI_REAL_EXPORT_SENTINEL_20260819 \
  -o paic-gemini-real.sanitized.json
```

Again, share only the probe report and the human-reviewed sanitized specimen.

## Probe output contract

Successful stdout contains only fields like:

```json
{
  "ok": true,
  "provider": "claude",
  "json_documents_scanned": 2,
  "html_documents_seen": 0,
  "matched_records": 1,
  "sanitized_specimen_sha256": "...",
  "sanitized_specimen_bytes": 1234,
  "output_file": "paic-claude-real.sanitized.json",
  "raw_export_not_copied": true
}
```

The report intentionally does not contain the raw archive path, archive member names, account identity, conversation title, timestamps, or message text.

## What counts as real validation

A provider is not marked real-export validated merely because the probe finds a record. Completion requires:

1. the sanitized real-derived specimen to be recognized by the intended adapter, or a narrowly evidenced adapter fix;
2. expected user/assistant ordering and sentinel tail markers;
3. content-free integrity evidence;
4. a synthetic regression fixture reproducing any newly observed structural shape without real account data;
5. adapter documentation updated to distinguish verified real shape from compatibility-only shape.
