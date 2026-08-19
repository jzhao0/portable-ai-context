# Claude public-share page validation

Tracking issue: #68

Portable AI Context does not currently claim a Claude shared-page adapter. Anthropic documents public chat snapshots for personal Claude plans, but does not publish a stable DOM schema that PAIC can safely parse.

The first validation therefore uses a deliberately non-sensitive **local browser DOM contract probe**. PAIC does not crawl or bypass access controls on `claude.ai/share/...`.

## First-party sharing boundary

Anthropic's current Help Center documents the following behavior for public chat sharing:

- a personal-plan user can create a shareable chat snapshot;
- anyone with the link can view that shared snapshot;
- the snapshot contains messages sent before sharing and can include artifacts;
- later messages remain private until the snapshot is updated;
- attached files themselves are not included in the shared snapshot;
- raw MCP tool-call data remains hidden; only final chat output/conversation is visible;
- Team/Enterprise chat sharing is organization-scoped rather than public.

Official reference:

- https://support.claude.com/en/articles/10593882-share-and-unshare-chats

The first PAIC shared-page contract therefore targets only **visible user/assistant conversation text**. It does not infer artifact-panel, attachment, hidden tool-call, or private authenticated-chat support.

## 1. Create a disposable public share

A volunteer with a working personal Claude account should create a brand-new chat containing no personal information, private project content, attachments, connectors, or other sensitive material.

Send exactly:

```text
PAIC_CLAUDE_SHARE_SENTINEL_20260819_USER. Reply exactly with the same marker, replacing the final word USER with ASSISTANT.
```

The desired assistant reply is exactly:

```text
PAIC_CLAUDE_SHARE_SENTINEL_20260819_ASSISTANT
```

Create a public share snapshot from that disposable conversation and open the share link in a Chromium or Firefox browser.

The public share URL itself does not need to be posted. It contains an opaque identifier and PAIC does not need that identifier as validation evidence.

## 2. Run the local structural probe

Review the committed probe first:

```text
tools/claude_share_dom_probe.js
```

Open Developer Tools on the disposable public share page, select **Console**, and paste/run that exact committed file.

The probe locally checks that:

- hostname is `claude.ai`;
- the current path has the `/share/<opaque>` shape;
- the fixed user sentinel occurs exactly once;
- the fixed assistant sentinel occurs exactly once.

The actual path/share identifier is never copied into the report. Only the boolean `share_route_matches` is returned.

## Privacy contract

The probe searches the local DOM only to find the two fixed sentinel text nodes. Non-sentinel text is never emitted.

The report may contain:

- `claude.ai`;
- `share_route_matches: true/false`;
- `USER` / `ASSISTANT` labels;
- match counts;
- HTML tag names;
- short CSS class tokens that pass opaque-token rejection;
- a small allowlist of short structural semantic attributes;
- `has_id: true/false` without any DOM ID value;
- child-element counts;
- a sanitized nearest-common-ancestor fingerprint.

The probe does **not** export:

- the `/share/<opaque>` path or share identifier;
- normal conversation text;
- page title;
- DOM ID values;
- cookies;
- local/session storage;
- auth/session state;
- network requests/responses;
- artifact contents;
- attachment contents;
- local filesystem paths.

It makes no network request.

## Expected report shape

Exact structural values depend on the current Claude frontend, but stdout has this top-level shape:

```json
{
  "ok": true,
  "probe": "paic-claude-share-dom-contract-v1",
  "hostname": "claude.ai",
  "expected_hostname": "claude.ai",
  "host_matches": true,
  "share_route_matches": true,
  "sentinels": {
    "user": {
      "marker": "USER",
      "match_count": 1,
      "unique_match": true,
      "ancestor_chain": []
    },
    "assistant": {
      "marker": "ASSISTANT",
      "match_count": 1,
      "unique_match": true,
      "ancestor_chain": []
    }
  },
  "nearest_common_ancestor": null,
  "privacy": {
    "share_identifier_exported": false,
    "normal_message_text_exported": false,
    "page_title_exported": false,
    "ids_exported": false,
    "cookies_or_storage_read": false,
    "network_requests_made": false,
    "auth_or_session_data_read": false,
    "artifact_or_attachment_content_exported": false
  }
}
```

If `ok` is false, do not modify the page or broaden the probe into a whole-page scraper. Report only the content-free result and current browser/version.

## 3. Human-review before sharing

Inspect the JSON report before posting it anywhere.

Stop and do **not** share it if it unexpectedly contains:

- ordinary Claude conversation text;
- a name/email/account identity;
- the share URL or opaque share ID;
- a UUID or private identifier;
- private URL/query data;
- cookies/tokens/auth/session values;
- attachment/artifact content;
- a private local path.

If anything private appears, report only that the probe needs hardening; never paste the private value.

## 4. What happens after one safe live report

One human-reviewed disposable public-share report is enough to decide whether the current Claude share page exposes a narrow stable role/message-root signal.

If it does, #68 proceeds with:

1. a fully synthetic DOM fixture derived from the safe structural contract;
2. a dedicated Claude-share capture profile rather than weakening `role_attribute_v1`;
3. exact user/assistant selector/ordering tests and false-positive rejection;
4. the existing beginning/tail and `DOM completeness: not proven` review UI;
5. local canonical `{role,text}` JSONL download with no share URL/ID metadata;
6. `paic inspect` / `paic conform` validation;
7. one real disposable public-share smoke against the finished profile;
8. normal 10-job CI.

If no sufficiently stable public structural signal exists, PAIC should leave Claude shared-page support unimplemented rather than ship a broad arbitrary-page text scraper.

## Evidence boundary

A successful probe does not validate private/authenticated Claude chat pages, Team/Enterprise organization-only shares, attachments, artifacts as standalone objects, hidden MCP data, or historical DOM variants.
