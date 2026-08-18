# Gemini My Activity JSON adapter

Portable AI Context supports a deliberately narrow, local-only Gemini Apps activity input in the v0.1 alpha.

Google supports downloading Gemini Apps data through Google Takeout by selecting **My Activity** and filtering it to **Gemini Apps**. Google's published My Activity export schema documents JSON activity records with fields such as `header`, `title`, `time`, `products`, `details`, and attachment metadata. Google does not publish a stable Gemini-specific chat-thread JSON schema, so this adapter does not claim to reconstruct original Gemini conversation boundaries.

## Supported source form

The input must be a local `.json` file containing either:

1. one Google My Activity-style activity record; or
2. a top-level JSON array of activity records.

A record is considered Gemini activity when either:

- `header` is `Gemini` or `Gemini Apps`; or
- `products` contains `Gemini` or `Gemini Apps`.

The supported alpha text extraction subset is intentionally explicit:

- an English `title` beginning with `Prompted ` or `Prompted: ` contributes the remainder as a canonical user message;
- when present, `safeHtmlItem` entries shaped like `{"html": "..."}` contribute sanitized HTML text as canonical assistant messages;
- other fields are not treated as conversation text.

`safeHtmlItem` is treated as an alpha compatibility field, not as a Google-guaranteed public schema field. If Google changes the export shape, the adapter should fail conservatively rather than copy arbitrary fields.

## Ordering and snapshot metadata

Gemini activity records with parseable `time` values are sorted chronologically. Records without a parseable timestamp retain source order after timestamped records.

The canonical snapshot records:

- earliest parseable activity time as `created_at`;
- latest parseable activity time as `updated_at`;
- Gemini activity-record count as `raw_node_count`;
- count of records missing a parseable timestamp;
- an explicit marker that original chat-thread reconstruction is unavailable from this supported activity-stream subset.

The canonical title is the common Gemini activity `header` when all selected records use the same non-empty header; otherwise it is `Gemini Apps Activity`. This is an activity-stream label, not an invented original chat title.

## Canonical allowlist

Only the following information can cross into canonical output:

- Gemini product/header label for the activity-stream title;
- prompt text extracted from the supported `title` prefix;
- assistant text extracted from supported `safeHtmlItem[].html` blocks;
- parsed activity timestamps and record counts;
- source fingerprint, adapter format marker, and privacy scanner counts.

The adapter does **not** emit arbitrary source fields such as account or user identifiers, title URLs, location information, activity controls, details, attachments, audio/image file references, authorization/session fields, or non-Gemini activity records.

Secrets deliberately typed inside accepted prompt/response text remain conversation content and are handled by the existing body-secret scanner policy.

## Explicit limitations

- No authenticated Gemini scraping.
- No Google session/cookie/token copying.
- No undocumented backend API dependency.
- No reconstruction of original multi-turn chat boundaries from a flat activity export.
- No guaranteed preservation of original Gemini chat titles because the supported My Activity subset does not expose them.
- No localized prompt-prefix parsing beyond the documented English `Prompted` forms in this alpha slice.
- No image/audio/file attachment extraction.
- No AI API is required for extraction.
