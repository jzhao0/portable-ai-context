# Firefox feasibility for browser capture

Firefox is not a validated target for the first Portable AI Context extension release, but the MVP architecture was chosen to keep a Firefox port small.

## Feasible shared architecture

Mozilla's current WebExtensions documentation supports the same core permission model used by the Chromium MVP:

- Manifest V3;
- `activeTab` for temporary access after explicit user interaction;
- `scripting` plus `scripting.executeScript()` for one-off injection into the active tab.

This means the privacy architecture does not require a Firefox-specific persistent host-permission design.

## Work required before claiming Firefox support

1. Validate the Manifest V3 package in a current Firefox release.
2. Add/verify the required `browser_specific_settings.gecko` metadata for development and AMO packaging.
3. Decide whether to use the promise-based `browser.*` namespace directly or a small compatibility wrapper around the current Chromium-oriented `chrome.*` popup code.
4. Validate structured-clone differences in values returned by `scripting.executeScript()`.
5. Confirm local Blob-based JSONL downloads from the popup in Firefox without adding the downloads permission.
6. Run the same permission/threat-model checks and manual tail/completeness smoke tests used for Chromium.
7. Review Mozilla Add-ons data-collection declarations before store publication.

Until those steps are complete, documentation and UI should say **Chrome / Edge / Brave first** rather than "all browsers".

## Security invariants for a Firefox port

A port must not weaken the Chromium MVP contract:

- no `<all_urls>` or persistent wildcard host access merely for convenience;
- no cookies/webRequest/debugger/session APIs;
- no full-page HTML serialization;
- no network upload path;
- same role/text allowlist;
- same preview-before-download flow;
- same JSONL artifact accepted by `paic`;
- same hard-fail behavior instead of silent truncation.

## Primary API references

- Mozilla WebExtensions `permissions` / `activeTab` documentation: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/permissions
- Mozilla `scripting.executeScript()` documentation: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/scripting/executeScript
- Mozilla `scripting` API documentation: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/scripting
