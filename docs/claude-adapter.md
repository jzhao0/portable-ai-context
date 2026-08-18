# Claude JSON adapter

Portable AI Context supports a deliberately narrow, local-only Claude JSON input in the v0.1 alpha.

Anthropic's product supports exporting conversation data together with account/user data. Because account exports may contain material that is not conversation content, this adapter uses an explicit allowlist and never carries arbitrary source fields into the canonical model.

## Supported source forms

The input must be a local `.json` file containing exactly one supported Claude conversation record. The record may appear as:

1. a top-level conversation object;
2. a one-element top-level array; or
3. a `{"conversations": [record]}` wrapper containing one record.

A supported conversation record has a `chat_messages` array. Multiple conversation records in one input are rejected explicitly in the alpha adapter rather than selecting one silently.

Example structural subset:

```json
{
  "name": "Example conversation",
  "created_at": "2026-08-18T10:00:00Z",
  "updated_at": "2026-08-18T10:05:00Z",
  "chat_messages": [
    {"sender": "human", "text": "Hello"},
    {"sender": "assistant", "text": "Hi"}
  ]
}
```

The adapter also accepts `sender: "user"` as a user role. Message text may come from either a non-empty `text` string or a `content` list containing text blocks shaped like `{"type": "text", "text": "..."}`. Non-text blocks are ignored.

## Canonical allowlist

Only the following information can cross from the Claude source into the canonical conversation:

- conversation `name` or `title` -> canonical title;
- `created_at` / `updated_at` -> parsed snapshot timestamps when parseable;
- number of raw `chat_messages` -> `raw_node_count`;
- `human` / `user` / `assistant` sender plus extracted text -> canonical ordered messages;
- source fingerprint, adapter format marker, and privacy scanner counts.

Fields such as account/user identifiers, email addresses outside message bodies, organization data, session/auth data, message UUIDs, model/runtime fields, attachments, tool calls, thinking blocks, and system/runtime messages are not emitted.

Secrets deliberately typed inside an accepted user/assistant text body remain conversation content; the general privacy scanner can warn about suspicious body patterns without silently rewriting history.

## Unsupported in this slice

- authenticated Claude scraping;
- copying browser cookies, session credentials, or authorization headers;
- automatic selection from a multi-conversation export file;
- Claude shared-page HTML parsing;
- non-text attachment extraction.

Extraction is deterministic and local. No AI API is required.
