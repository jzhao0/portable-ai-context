from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "gemini_share_dom_probe.js"
DOC = ROOT / "docs" / "gemini-shared-page-validation.md"
ROADMAP = ROOT / "ROADMAP.md"

USER_SENTINEL = "PAIC_GEMINI_SHARE_SENTINEL_20260819_USER"
ASSISTANT_SENTINEL = "PAIC_GEMINI_SHARE_SENTINEL_20260819_ASSISTANT"


class GeminiShareDOMProbeContractTests(unittest.TestCase):
    def test_probe_is_local_content_safe_and_does_not_assume_final_route(self):
        text = PROBE.read_text(encoding="utf-8")

        self.assertIn(USER_SENTINEL, text)
        self.assertIn(ASSISTANT_SENTINEL, text)
        self.assertIn('const SAFE_ROUTE_LITERALS = new Set(["gemini", "share"])', text)
        self.assertIn('hostname === "g.co"', text)
        self.assertIn('hostname === "google.com"', text)
        self.assertIn('hostname.endsWith(".google.com")', text)
        self.assertIn('"<non-google-first-party>"', text)
        self.assertIn('"<redacted-segment>"', text)
        self.assertIn('"<route-too-deep>"', text)
        self.assertIn("document.createTreeWalker", text)
        self.assertIn("NodeFilter.SHOW_TEXT", text)
        self.assertIn("compareDocumentPosition", text)
        self.assertIn("user_precedes_assistant:", text)
        self.assertIn("google_first_party_host: firstPartyHost", text)
        self.assertIn("public_route_shape: sanitizedRouteShape", text)

        self.assertNotIn("const EXPECTED_HOST", text)
        self.assertNotIn("const SHARE_ROUTE_RE", text)
        self.assertNotIn("expected_hostname:", text)
        self.assertNotIn("expected_route", text)

    def test_probe_fails_closed_on_non_google_host_before_dom_scan(self):
        text = PROBE.read_text(encoding="utf-8")
        self.assertIn(
            "const userMatches = firstPartyHost ? findSentinelTextNodes(USER_SENTINEL) : [];",
            text,
        )
        self.assertIn(
            "const assistantMatches = firstPartyHost ? findSentinelTextNodes(ASSISTANT_SENTINEL) : [];",
            text,
        )
        self.assertIn(
            'const sanitizedRouteShape = firstPartyHost ? routeShape(location.pathname) : "<not-inspected>";',
            text,
        )

    def test_probe_does_not_export_sensitive_url_page_or_browser_state(self):
        text = PROBE.read_text(encoding="utf-8")

        for required in (
            "full_url_exported: false",
            "opaque_share_identifier_exported: false",
            "query_or_fragment_exported: false",
            "normal_message_text_exported: false",
            "page_title_exported: false",
            "dom_id_values_exported: false",
            "cookies_or_storage_read: false",
            "network_requests_made: false",
            "auth_or_session_data_read: false",
            "canvas_image_video_or_attachment_content_exported: false",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)

        # pathname is read only into a sanitizer; no raw path/href/referrer/title
        # field may be copied into the report.
        self.assertIn("routeShape(location.pathname)", text)
        self.assertNotIn("pathname:", text)
        self.assertNotIn("path:", text)
        self.assertNotIn("href:", text)
        self.assertNotIn("referrer:", text)

        forbidden = (
            "document.cookie",
            "document.title",
            "document.referrer",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "navigator.sendBeacon",
            "chrome.cookies",
            "chrome.storage",
            "browser.cookies",
            "browser.storage",
            "location.href",
            "location.search",
            "location.hash",
            "history.state",
            "innerHTML",
            "outerHTML",
            "element.id",
            'getAttribute("id")',
            "getAttribute('id')",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)

    def test_probe_only_exports_allowlisted_structural_attribute_values(self):
        text = PROBE.read_text(encoding="utf-8")
        for attribute in (
            '"role"',
            '"data-testid"',
            '"data-role"',
            '"data-author"',
            '"data-message-role"',
            '"data-message-author-role"',
            '"data-message-type"',
            '"aria-live"',
        ):
            with self.subTest(attribute=attribute):
                self.assertIn(attribute, text)
        self.assertIn('has_id: element.hasAttribute("id")', text)
        self.assertIn("isSafeStructuralValue", text)
        self.assertIn("MAX_SAFE_VALUE_LENGTH", text)
        self.assertIn("MAX_CLASS_TOKENS", text)
        self.assertIn("MAX_ANCESTOR_DEPTH", text)

    def test_probe_does_not_claim_redirect_signed_out_or_final_contract(self):
        text = PROBE.read_text(encoding="utf-8")
        self.assertIn("short_link_redirect_observed_by_probe: false", text)
        self.assertIn("signed_out_state_proven_by_probe: false", text)
        self.assertIn("final_route_contract_proven: false", text)

    def test_validation_doc_preserves_first_party_and_live_evidence_boundaries(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn(USER_SENTINEL, text)
        self.assertIn(ASSISTANT_SENTINEL, text)
        self.assertIn("support.google.com/gemini/answer/13743730", text)
        self.assertIn("must not assume that `g.co/gemini/share/...` is the final rendered page URL", text)
        self.assertIn("signed-out private/incognito", text)
        self.assertIn("Record manually whether the browser visibly redirected", text)
        self.assertIn("The probe does **not** export:", text)
        self.assertIn("It makes no network request", text)
        self.assertIn("DOM completeness: not proven", text)
        self.assertIn("text-only", text)
        self.assertIn("require deliberately non-sensitive live evidence under #70", text)

    def test_roadmap_tracks_gemini_shared_page_issue_without_marking_complete(self):
        text = ROADMAP.read_text(encoding="utf-8")
        self.assertIn("- [ ] Gemini page/thread adapter when a reliable source contract exists (#70)", text)
        self.assertNotIn("- [x] Gemini page/thread adapter when a reliable source contract exists (#70)", text)


if __name__ == "__main__":
    unittest.main()
