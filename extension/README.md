# Portable AI Context browser capture extension

This directory contains the first privacy-safe browser-side capture path for Portable AI Context.

## Target browsers

The MVP targets Chromium Manifest V3 browsers first:

- Google Chrome;
- Microsoft Edge;
- Brave.

Firefox feasibility is documented separately in [`../docs/browser-extension-firefox.md`](../docs/browser-extension-firefox.md).

## Permission model

The extension requests only:

```json
"permissions": ["activeTab", "scripting"]
```

It deliberately has no persistent `host_permissions` / `<all_urls>` access and does not request `cookies`, `webRequest`, `tabs`, `storage`, `downloads`, clipboard, debugger, or native-messaging permissions.

`activeTab` is granted temporarily when the user explicitly opens/invokes the extension on the current tab. `scripting.executeScript()` then runs the packaged capture function once in that tab.

The extension performs no network requests and stores no capture in extension storage. The in-memory capture is cleared when the popup is cleared or destroyed.

## Current DOM adapter

The initial `role_attribute_v1` adapter is deliberately narrow. It selects only DOM nodes with:

```text
data-message-author-role="user"
data-message-author-role="assistant"
```

Unsupported roles are ignored. If no supported role-marked conversation DOM exists, capture fails explicitly. There is no whole-page HTML fallback.

Before extracting text, the adapter clones each selected message root and removes script/style/template/form/control/SVG/canvas elements. It reads text from the clone only; page HTML is never serialized into the artifact and page scripts are never copied or executed as capture data.

Because platform DOM is not a stable public API, this adapter is experimental and intentionally fails conservatively when the expected role markers are absent.

## Capture contract

The in-memory result follows [`../schemas/browser-capture.schema.json`](../schemas/browser-capture.schema.json):

```json
{
  "ok": true,
  "schema_version": "paic-browser-capture-1",
  "adapter": "role_attribute_v1",
  "message_count": 2,
  "ignored_role_nodes": 0,
  "empty_role_nodes": 0,
  "messages": [
    {"role": "user", "text": "Hello", "index": 0},
    {"role": "assistant", "text": "Hi", "index": 1}
  ]
}
```

No page URL, page title, cookies, account identifiers, request headers, session/bootstrap objects, or unrelated DOM/runtime state are part of the contract.

## Preview-before-download flow

1. Open the target conversation and click the extension.
2. Click **Inspect conversation**.
3. Review:
   - canonical message count;
   - adapter used;
   - last-user preview;
   - last-assistant preview;
   - ignored/empty node counts.
4. Only then does **Download JSONL** become enabled.
5. The generated filename contains a timestamp only, not the page title or URL.

Tail previews are intentionally truncated for UI display only. The downloaded canonical message text is not truncated.

## Export format

The extension exports local JSONL with one allowlisted object per line:

```json
{"role":"user","text":"Hello"}
{"role":"assistant","text":"Hi"}
```

This is directly accepted by the existing `paic` JSONL adapter:

```bash
paic inspect paic-capture-....jsonl
paic extract paic-capture-....jsonl -o out
paic bundle paic-capture-....jsonl -o project.aicb
```

The download is produced from a local browser `Blob`; the extension does not upload the artifact and therefore does not need the browser downloads API permission.

## Local development install

For Chromium-family browsers, load `extension/` as an unpacked extension from the browser's extension-development page. This directory is source code, not a signed store package.

## Security boundary

The extension captures conversation text; it does not decide whether that text is safe to publish. A secret deliberately typed inside a user/assistant message remains conversation content. Review the preview and use the core `paic inspect` privacy report before sharing artifacts.

See [`../docs/browser-extension-threat-model.md`](../docs/browser-extension-threat-model.md) for the full threat model.
