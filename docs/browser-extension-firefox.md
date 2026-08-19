# Firefox validation for browser capture

Tracking issue: #64

Firefox is now covered by an automated **Manifest V3 package/lint compatibility gate**, but PAIC does not claim Firefox live-runtime support until the separate content-safe browser smoke in #64 is completed.

This distinction is intentional:

```text
web-ext lint/build + package inspection  !=  live Firefox capture validation
```

## Shared architecture

Mozilla's current WebExtensions documentation supports the core permission model used by the PAIC Chromium extension:

- Manifest V3;
- `activeTab` for temporary target-page access after explicit user interaction;
- `scripting` plus `scripting.executeScript()` for one-off injection into that active tab.

The shared PAIC manifest therefore retains exactly:

```json
"permissions": ["activeTab", "scripting"]
```

There is still no persistent `host_permissions`, `<all_urls>`, cookies, webRequest, debugger, history, storage, or downloads permission.

## Firefox Manifest V3 metadata

Firefox Manifest V3 signing/distribution requires an extension ID. New AMO submissions also require a data-collection declaration.

The shared manifest contains:

```json
"browser_specific_settings": {
  "gecko": {
    "id": "portable-ai-context-capture@jzhao0.github.io",
    "data_collection_permissions": {
      "required": ["none"]
    }
  }
}
```

The Gecko ID is an extension identifier, not a real email address or credential.

`required: ["none"]` describes PAIC's current browser extension behavior: it does not collect and transmit captured data outside the extension for external storage or processing. Conversation text is held only in popup memory and exported through a local Blob download after explicit user action.

The Chromium source tree remains shared. Current Chrome documentation ignores `browser_specific_settings`; PAIC does not maintain a second forked Firefox copy of the extension source merely for this metadata.

## Cross-browser extension API namespace

The popup uses one tiny runtime selector:

```javascript
const extensionApi = typeof browser !== "undefined" ? browser : chrome;
```

The two asynchronous calls are then made through that selected namespace:

```text
extensionApi.tabs.query(...)
extensionApi.scripting.executeScript(...)
```

This keeps Firefox on the native Promise-oriented `browser.*` path and Chromium on the existing `chrome.*` path. No external WebExtension polyfill or new runtime dependency is added.

The value returned by PAIC's injected capture function is a plain structured object containing strings, integers, booleans, arrays, and objects. That shape is compatible with Firefox's structured-clone requirement for `scripting.executeScript()` results, but the package/static gate is not a substitute for observing the result in a live Firefox process.

## Automated package gate

The normal GitHub Actions matrix remains 10 jobs total. The existing Ubuntu `package` job additionally uses Node.js 22 and pinned Mozilla `web-ext@10.5.0` to run:

```text
web-ext lint --warnings-as-errors
web-ext build
```

The resulting ZIP is then independently reopened by:

```text
tools/firefox_extension_package_smoke.py
```

That smoke requires:

- exactly one Firefox ZIP;
- top-level `manifest.json`, `popup.html`, `popup.css`, and `popup.js`;
- Manifest V3;
- exactly `activeTab` + `scripting` permissions;
- no `host_permissions` / `optional_host_permissions`;
- the reviewed Gecko extension ID;
- `data_collection_permissions.required = ["none"]`;
- no `strict_min_version` claim yet.

A package that fails any of these checks fails the normal CI package job.

## Why `strict_min_version` is not set yet

Mozilla documents minimum-version compatibility checking through `web-ext lint` when `strict_min_version` is declared. PAIC deliberately does **not** choose that runtime baseline from static reasoning alone.

The browser APIs required by the architecture have documented Firefox support, but the remaining roadmap item is explicitly **runtime/package validation**. The exact Firefox version used for the first live PAIC smoke will become the evidence-backed baseline. After that smoke, the project can decide whether to record a `strict_min_version` and lock it in lint/tests.

This avoids turning an inferred compatibility floor into a tested-support claim.

## Live Firefox gate still required

Before the ROADMAP item can be checked complete, run a deliberately non-sensitive Firefox Desktop smoke that verifies all of the following in an actual Firefox process:

1. the extension loads temporarily or as an appropriate test package;
2. **Inspect conversation** executes against the active tab;
3. the expected fixed test messages are returned in DOM order;
4. first/tail previews and the permanent `DOM completeness: not proven` notice render correctly;
5. the local Blob-based JSONL download succeeds without adding the downloads permission;
6. the downloaded JSONL passes `paic inspect` and `paic conform`;
7. no unexpected authority/permission is needed.

Only content-free evidence should be recorded:

```text
Firefox version
extension loaded: yes/no
inspect succeeded: yes/no
message count
fixed sentinel order correct: yes/no
completeness warning visible: yes/no
Blob JSONL download succeeded: yes/no
paic inspect/conform: pass/fail
```

Do not publish normal conversation text, account identity, page URLs/query data, browser-profile data, or private local paths.

## Security invariants

Firefox validation must not weaken the existing browser-capture contract:

- no `<all_urls>` or persistent wildcard host access;
- no cookies/webRequest/debugger/session APIs;
- no full-page HTML serialization;
- no network upload path or analytics;
- same role/text allowlist;
- same beginning/tail preview-before-download flow;
- same `DOM completeness: not proven` boundary;
- same JSONL artifact accepted by `paic`;
- same hard-fail behavior instead of silent truncation.

## Primary references

- Mozilla `browser_specific_settings` / Gecko ID / data collection declaration: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/browser_specific_settings
- Mozilla `scripting.executeScript()`: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/scripting/executeScript
- Mozilla `scripting` + `activeTab` permission model: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/scripting
- Mozilla Chrome incompatibilities / `browser.*` vs `chrome.*`: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Chrome_incompatibilities
- Firefox Extension Workshop `web-ext`: https://extensionworkshop.com/documentation/develop/getting-started-with-web-ext/
