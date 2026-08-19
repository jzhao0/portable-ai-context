from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "claude_share_dom_probe.js"
DOC = ROOT / "docs" / "claude-shared-page-validation.md"
ROADMAP = ROOT / "ROADMAP.md"

USER_SENTINEL = "PAIC_CLAUDE_SHARE_SENTINEL_20260819_USER"
ASSISTANT_SENTINEL = "PAIC_CLAUDE_SHARE_SENTINEL_20260819_ASSISTANT"


class ClaudeShareDOMProbeContractTests(unittest.TestCase):
    def test_probe_is_local_content_safe_and_does_not_export_share_identifier(self):
        text = PROBE.read_text(encoding="utf-8")

        self.assertIn(USER_SENTINEL, text)
        self.assertIn(ASSISTANT_SENTINEL, text)
        self.assertIn('const EXPECTED_HOST = "claude.ai"', text)
        self.assertIn("document.createTreeWalker", text)
        self.assertIn("NodeFilter.SHOW_TEXT", text)
        self.assertIn("share_route_matches: shareRouteMatches", text)
        self.assertIn("share_identifier_exported: false", text)
        self.assertIn("normal_message_text_exported: false", text)
        self.assertIn("page_title_exported: false", text)
        self.assertIn("ids_exported: false", text)
        self.assertIn("cookies_or_storage_read: false", text)
        self.assertIn("network_requests_made: false", text)
        self.assertIn("auth_or_session_data_read: false", text)
        self.assertIn("artifact_or_attachment_content_exported: false", text)

        # Reading pathname locally only to produce a boolean share-route check is
        # allowed. The path itself must never be placed into a report field.
        self.assertIn(".test(location.pathname)", text)
        self.assertNotIn("pathname:", text)
        self.assertNotIn("path:", text)
        self.assertNotIn("href:", text)

        forbidden = (
            "document.cookie",
            "document.title",
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
        ):
            with self.subTest(attribute=attribute):
                self.assertIn(attribute, text)
        self.assertIn('has_id: element.hasAttribute("id")', text)
        self.assertIn("isSafeStructuralValue", text)
        self.assertIn("MAX_SAFE_VALUE_LENGTH", text)

    def test_validation_doc_preserves_first_party_and_evidence_boundaries(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn(USER_SENTINEL, text)
        self.assertIn(ASSISTANT_SENTINEL, text)
        self.assertIn("support.claude.com/en/articles/10593882-share-and-unshare-chats", text)
        self.assertIn("The actual path/share identifier is never copied", text)
        self.assertIn("does not export", text)
        self.assertIn("makes no network request", text)
        self.assertIn("private/authenticated Claude chat pages", text)
        self.assertIn("DOM completeness: not proven", text)
        self.assertIn("rather than ship a broad arbitrary-page text scraper", text)

    def test_roadmap_tracks_claude_shared_page_issue(self):
        text = ROADMAP.read_text(encoding="utf-8")
        self.assertIn("- [ ] Claude shared/page adapter (#68)", text)


if __name__ == "__main__":
    unittest.main()
