# Gemini public-share page discovery and validation

Tracking issue: #70

PAIC does **not** currently claim a Gemini public-share page adapter. This document defines the privacy-safe evidence gate that must be completed before a dedicated capture profile can be added.

## First-party sharing boundary

Google's Gemini Apps Help documents a public conversation-sharing flow:

- sharing a response can create a public link for the entire conversation;
- the public link is presented as `g.co/gemini/share/...`;
- anyone with the link can read and reshare the shared chat;
- the shared page is a snapshot of the conversation as it appeared when the public link was created;
- AI-generated Canvas documents, images, and videos can also be present in a shared chat;
- Google states that the creator's name/account is not added to the public URL or shared chat page.

Primary reference:

- https://support.google.com/gemini/answer/13743730

That documentation establishes the public **entry link and sharing semantics**. It does not document a stable final redirected hostname/path or a supported DOM message schema for PAIC.

The first adapter therefore must not assume that `g.co/gemini/share/...` is the final rendered page URL.

## Deliberately non-sensitive sentinel conversation

Create a new ordinary Gemini conversation containing no personal, account, or project information.

Send exactly:

```text
PAIC_GEMINI_SHARE_SENTINEL_20260819_USER. Reply exactly with the same marker, replacing the final word USER with ASSISTANT.
```

The intended assistant reply is:

```text
PAIC_GEMINI_SHARE_SENTINEL_20260819_ASSISTANT
```

For the first structural test, do not use:

- a Gem;
- uploaded files or images;
- Canvas;
- connectors;
- private or work/school data.

Then create the public conversation link through Gemini's official Share conversation flow.

## Live browser procedure

Use a signed-out private/incognito browser window when possible so the test clearly exercises a public page rather than authenticated account UI.

1. Record the browser name/version locally.
2. Paste/open the disposable `g.co/gemini/share/...` public link.
3. Record manually whether the browser visibly redirected away from the `g.co` entry URL.
4. Wait until both fixed sentinel messages are visibly rendered.
5. Open DevTools on the final rendered page.
6. Paste the complete contents of:

```text
tools/gemini_share_dom_probe.js
```

7. Run it once.
8. Review the JSON report before sharing it.

The probe copies its sanitized report through the DevTools `copy()` helper when that helper is available.

Do not post the disposable public link or opaque share identifier unless you intentionally want the public snapshot indexed/shared more broadly.

## What the probe does

The probe intentionally does **not** contain an expected final Gemini hostname or final share-route regex.

Instead it:

1. reads the final page hostname;
2. allows DOM inspection only on `g.co`, `google.com`, or a `*.google.com` hostname;
3. reports the final hostname only when it belongs to that first-party Google host class;
4. derives a sanitized route shape from `location.pathname` locally;
5. preserves only the public route literals `gemini` and `share`;
6. replaces every other route segment with `<redacted-segment>`;
7. refuses to summarize a route deeper than the configured segment bound and reports `<route-too-deep>` instead;
8. searches rendered text nodes only for the two fixed sentinels;
9. requires each sentinel exactly once for `ok=true`;
10. reports whether the user sentinel precedes the assistant sentinel in DOM order;
11. reports only bounded tag/class/allowlisted semantic-attribute fingerprints around those two nodes;
12. reports a nearest common ancestor structural fingerprint when available.

If the final page is not on the Google first-party host class, the probe does not inspect the page DOM and reports a generic `<non-google-first-party>` hostname marker.

## Data the probe does not export

The probe does **not** export:

- the full public URL;
- the opaque share identifier;
- URL query or fragment data;
- normal Gemini conversation text;
- Google account identity;
- page title;
- DOM `id` values;
- cookies;
- local/session storage;
- auth/session/bootstrap data;
- network request/response payloads;
- Canvas, image, video, uploaded-file, or attachment content.

It makes no network request.

The boolean `has_id` reports only that an element has an `id` attribute; the value is never copied.

## Route evidence semantics

Example sanitized shapes may look like:

```text
/share/<redacted-segment>
/gemini/share/<redacted-segment>
/<redacted-segment>/<redacted-segment>
```

Those examples are not asserted provider contracts. The actual disposable live result determines what can later be documented.

The probe deliberately does not claim that it observed the original `g.co` redirect. Once JavaScript runs on the final page, browser history/referrer data could itself expose the share identifier and is outside the safe probe contract.

Likewise, the probe cannot prove that the tester is signed out. The signed-out/private-window state is a manual live-evidence observation.

The report therefore keeps these fields false until external live review establishes them separately:

```text
short_link_redirect_observed_by_probe: false
signed_out_state_proven_by_probe: false
final_route_contract_proven: false
```

## Safe report contents

A report may include only:

- `probe` identifier;
- final first-party hostname or `<non-google-first-party>`;
- `google_first_party_host` boolean;
- sanitized `public_route_shape`;
- fixed-sentinel match counts;
- fixed-sentinel DOM ordering;
- safe ancestor tag/class/semantic-attribute fingerprints;
- structural `has_id` booleans and child counts;
- explicit privacy/evidence-boundary booleans.

Before sharing a report, verify that no opaque identifier or normal conversation text appears anywhere in it.

If anything private appears, do not paste the leaked value. Report only that the sanitizer/probe needs hardening.

## Phase B after real evidence

A dedicated Gemini public-share capture profile can be implemented only after the disposable live test establishes a stable first-party final route and reliable user/assistant message-root/role structure.

Then:

```text
first-party public short link
→ signed-out/private live redirect observation
→ sanitized DOM probe
→ human-reviewed structural evidence
→ narrow text-only selector/role contract
→ synthetic DOM regression fixture
→ dedicated local capture profile
→ second disposable public-share smoke
→ canonical JSONL
→ paic inspect + paic conform
→ normal 10-job CI
```

The first profile must remain text-only. Do not infer support for Canvas, images/video, Gem instructions, uploads, or continuation controls from the ordinary text sentinel test.

Use the existing browser-extension authority and UX boundaries:

```text
activeTab + scripting
local explicit capture
no persistent host permissions
beginning/tail review
DOM completeness: not proven
canonical {role,text} JSONL
```

The public link/share ID must not be added to the downloaded PAIC artifact.

## Evidence boundary

Static tests for this probe establish only that the discovery code follows the reviewed privacy contract. They do not prove:

- where a real `g.co/gemini/share/...` link currently redirects;
- that the final route is stable;
- that a signed-out user can read the tested link;
- any Gemini public-share DOM selector;
- message completeness beyond the two rendered sentinels;
- Canvas/image/video/upload fidelity;
- Gemini public-share adapter support.

Those claims require deliberately non-sensitive live evidence under #70.
