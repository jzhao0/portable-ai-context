# Browser capture extension threat model

The browser extension is a capture transport, not a trusted source of truth and not a migration compiler. Its security goal is to minimize what browser/page state can cross into Portable AI Context artifacts.

## Assets to protect

The extension should not disclose or persist:

- browser cookies;
- Authorization or other request headers;
- account/session/bootstrap objects;
- authentication tokens;
- unrelated page DOM/runtime state;
- browsing history or persistent cross-site access.

Conversation text is a separate class of data. User/assistant text selected by the capture allowlist is intentionally exported, including secrets the user deliberately typed into that text.

## Trust boundaries

### Browser extension package

Packaged extension code is trusted to implement the capture allowlist. The MVP requests only `activeTab` and `scripting`, with no persistent host permission. Access begins only after an explicit user invocation on the active tab and ends with the browser's active-tab permission lifetime.

### Web page / conversation DOM

The page is untrusted. A page can alter its DOM, imitate expected role attributes, inject adversarial transcript text, or attempt to exhaust extension resources. DOM presence is therefore evidence of what was rendered, not cryptographic proof that a platform authored the content.

### Captured transcript text

Captured user/assistant text is untrusted data. It may contain prompt injection, code, HTML-looking text, URLs, credentials, or instructions aimed at a downstream model. The extension never evaluates captured text as JavaScript or extension markup.

The core migration compiler separately instructs model backends to treat old conversation content as data rather than as higher-priority instructions.

## Threats and mitigations

### Persistent browser surveillance

**Threat:** an extension with broad host access could continuously inspect unrelated tabs.

**Mitigation:** no `<all_urls>` or persistent `host_permissions`; use `activeTab` only after explicit user action. No history/tabs/storage permissions are requested.

### Cookie/session/auth extraction

**Threat:** browser APIs or page-runtime scraping could expose credentials.

**Mitigation:** the manifest does not request cookies, webRequest, debugger, storage, or broad host permissions. The capture contract has no fields for cookies, headers, URL, account identity, bootstrap/session objects, or arbitrary page state. The injected function reads only allowlisted DOM role nodes.

### Whole-page serialization leakage

**Threat:** saving `document.documentElement.outerHTML` could preserve hidden account metadata, bootstrap JSON, script state, CSRF tokens, or unrelated page content.

**Mitigation:** whole-page HTML serialization is forbidden. The MVP queries only `data-message-author-role` roots for `user` / `assistant`, clones those roots, removes executable/control/non-text UI elements, and emits normalized text only.

### Malicious or drifting DOM

**Threat:** a page may imitate role attributes or platform DOM changes may cause incomplete capture.

**Mitigation:** unsupported roles are ignored; absence of the narrow selector is a hard failure rather than a fallback to broad scraping. The popup reports canonical message count, ignored/empty role-node counts, and last user/assistant previews before download. Users should compare these tail previews with the visible conversation.

The extension does not claim source authenticity. Integrity hashes generated later by `paic` prove artifact consistency, not that the webpage itself was honest.

### Prompt injection in transcript text

**Threat:** captured text may contain instructions such as "ignore previous rules" aimed at the downstream compiler/model.

**Mitigation:** the extension treats all captured text as inert strings. It does not execute or interpret transcript instructions. Compiler system prompts maintain a separate instruction boundary and explicitly treat historical conversation as data.

### Secret-bearing conversation text

**Threat:** a real API key or credential may have been typed into a user/assistant message.

**Mitigation:** body text is not silently rewritten because that would corrupt conversation history. The popup warns before download that captured message text is exported verbatim. The user can run `paic inspect` afterward; the core privacy scanner reports suspicious body-secret pattern counts without printing secret values.

### Executable HTML inside message DOM

**Threat:** script/style/template or UI elements inside selected message roots could be copied into the artifact or influence preview rendering.

**Mitigation:** extraction operates on a detached clone; script/style/noscript/template/form/control/SVG/canvas elements are removed before text extraction. Popup values are assigned with `textContent`, not `innerHTML`.

### Resource exhaustion / silent truncation

**Threat:** a malicious or pathological page could expose an enormous number of role nodes or a huge message, causing browser instability. A defensive limit could silently lose the tail.

**Mitigation:** the MVP hard-fails instead of truncating when it sees more than 10,000 role-marked roots or a supported message over 5,000,000 characters. Preview truncation is UI-only and explicitly marked; downloaded message text is not preview-truncated.

### Accidental source-identity disclosure

**Threat:** filenames or metadata could expose a private conversation title/URL.

**Mitigation:** the capture contract contains neither page URL nor page title. Download filenames contain only a generic prefix plus timestamp.

### Unintended network exfiltration

**Threat:** captured text could be sent to an external service.

**Mitigation:** the MVP contains no `fetch`, XMLHttpRequest, WebSocket, analytics, remote code, or upload path. Export is generated as a local Blob from popup memory.

## Out of scope / residual risk

- A compromised browser or maliciously modified extension package can bypass these guarantees.
- The DOM adapter can become stale as platform markup changes.
- The extension cannot prove that displayed page content came from the claimed AI provider.
- The extension does not redact secrets typed into actual conversation text.
- Attachments, images, audio, canvases, hidden reasoning, tool calls, and platform runtime metadata are intentionally excluded from this MVP.

These constraints favor conservative failure over broad capture.
