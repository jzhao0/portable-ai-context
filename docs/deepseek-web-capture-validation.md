# DeepSeek Web capture contract validation

Issue: #58

Portable AI Context does not currently claim a first-party DeepSeek export-file adapter. The DeepSeek web product has not exposed a stable documented single-conversation JSON/HTML export contract that PAIC can safely parse, so the first step is a deliberately non-sensitive **live DOM contract probe**.

This probe is for selector/role research only. It is not the final DeepSeek adapter and it must not be used on a private conversation for public evidence.

## Privacy boundary

The committed probe in [`tools/deepseek_dom_probe.js`](../tools/deepseek_dom_probe.js) is intentionally content-safe:

- it searches only for two fixed PAIC sentinel markers;
- it does not export ordinary conversation text;
- it does not export DOM `id` values;
- it does not read cookies, local storage, session storage, IndexedDB, auth/session state, or network payloads;
- it does not make network requests;
- it reports only the page hostname, structural tag/class information, a small allowlist of safe semantic attributes, counts, and whether the two sentinel markers were found exactly once.

The script may inspect text nodes locally in order to find the fixed markers, but non-sentinel text is never included in the report.

Do not modify the probe to dump `innerHTML`, `outerHTML`, whole message text, request bodies, storage values, or application state.

## 1. Create a disposable test conversation

Use the official DeepSeek web app at `chat.deepseek.com` and create a brand-new conversation containing no personal information, private project content, uploaded files, or account-specific material.

Send exactly:

```text
PAIC_DEEPSEEK_CAPTURE_SENTINEL_20260819_USER. Reply exactly with the same marker, replacing the final word USER with ASSISTANT.
```

The desired assistant reply is exactly:

```text
PAIC_DEEPSEEK_CAPTURE_SENTINEL_20260819_ASSISTANT
```

If DeepSeek adds extra text, do not edit the conversation. The structural probe can still be useful as long as the assistant marker occurs exactly once.

## 2. Open the browser console

Use a Chromium browser where the test conversation is visible.

Open Developer Tools and select **Console**. Review the committed source before running it:

```text
tools/deepseek_dom_probe.js
```

Paste/run that exact file in the console. Do not run a modified copy that reads storage, cookies, requests, or full page HTML.

The probe is expected to print JSON and, when the Chromium DevTools `copy()` helper is available, copy the same JSON to the clipboard.

## 3. Expected report shape

Values will vary with the current DeepSeek frontend, but the top-level shape is:

```json
{
  "ok": true,
  "probe": "paic-deepseek-dom-contract-v1",
  "hostname": "chat.deepseek.com",
  "expected_hostname": "chat.deepseek.com",
  "host_matches": true,
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
    "normal_message_text_exported": false,
    "ids_exported": false,
    "cookies_or_storage_read": false,
    "network_requests_made": false,
    "auth_or_session_data_read": false
  }
}
```

The `ancestor_chain` entries may contain:

- `tag`;
- short CSS class tokens;
- allowlisted semantic attributes such as `role`, `data-testid`, or message-role attributes when their values are short structural literals;
- `has_id: true/false` without the ID value;
- child element counts.

## 4. Human-review before sharing

Before posting or pasting the report anywhere, inspect it manually.

Expected safe content:

- `chat.deepseek.com`;
- `USER` / `ASSISTANT` labels;
- HTML tag names;
- CSS class tokens;
- public structural role/test attributes;
- integer counts and booleans.

Stop and do **not** share the report if it unexpectedly contains:

- normal conversation text;
- a name or email address;
- account/conversation IDs or UUIDs;
- private URLs or URL query strings;
- cookies, tokens, auth/session values;
- local/session storage values;
- uploaded file names/content;
- private local filesystem paths.

Report only that the probe needs hardening if any such value appears.

## 5. What happens after one safe live report

A single deliberately non-sensitive live report is enough to determine whether DeepSeek exposes a narrow stable DOM signal suitable for a dedicated PAIC capture profile.

If it does, #58 will proceed with:

1. a synthetic DOM regression fixture derived only from the safe structural contract;
2. a dedicated DeepSeek capture profile rather than weakening the generic `role_attribute_v1` profile;
3. explicit user/assistant ordering tests and false-positive rejection;
4. a real sentinel smoke that downloads canonical JSONL;
5. `paic inspect` / `paic conform` validation of that JSONL;
6. normal 10-job CI.

If the live page exposes no sufficiently stable role/message-root contract, PAIC should leave DeepSeek marked unsupported rather than ship a broad arbitrary-page scraper.
