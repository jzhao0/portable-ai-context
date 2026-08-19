from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "deepseek_dom_probe.js"
DOC = ROOT / "docs" / "deepseek-web-capture-validation.md"
ROADMAP = ROOT / "ROADMAP.md"

USER_SENTINEL = "PAIC_DEEPSEEK_CAPTURE_SENTINEL_20260819_USER"
ASSISTANT_SENTINEL = "PAIC_DEEPSEEK_CAPTURE_SENTINEL_20260819_ASSISTANT"


class DeepSeekDOMProbeContractTests(unittest.TestCase):
    def test_probe_is_content_safe_and_network_free(self):
        text = PROBE.read_text(encoding="utf-8")

        self.assertIn(USER_SENTINEL, text)
        self.assertIn(ASSISTANT_SENTINEL, text)
        self.assertIn('const EXPECTED_HOST = "chat.deepseek.com"', text)
        self.assertIn("document.createTreeWalker", text)
        self.assertIn("NodeFilter.SHOW_TEXT", text)
        self.assertIn("normal_message_text_exported: false", text)
        self.assertIn("ids_exported: false", text)
        self.assertIn("cookies_or_storage_read: false", text)
        self.assertIn("network_requests_made: false", text)
        self.assertIn("auth_or_session_data_read: false", text)

        forbidden = (
            "document.cookie",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "navigator.sendBeacon",
            "chrome.cookies",
            "chrome.storage",
            "location.href",
            "location.pathname",
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

    def test_probe_only_exports_allowlisted_semantic_attribute_values(self):
        text = PROBE.read_text(encoding="utf-8")
        expected_attributes = (
            '"role"',
            '"data-testid"',
            '"data-role"',
            '"data-author"',
            '"data-message-role"',
            '"data-message-author-role"',
            '"data-message-type"',
        )
        for attribute in expected_attributes:
            with self.subTest(attribute=attribute):
                self.assertIn(attribute, text)

        self.assertIn("has_id: element.hasAttribute(\"id\")", text)
        self.assertIn("isSafeStructuralValue", text)
        self.assertIn("MAX_SAFE_VALUE_LENGTH", text)

    def test_validation_doc_uses_non_overlapping_sentinels_and_strict_privacy_boundary(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertIn(USER_SENTINEL, text)
        self.assertIn(ASSISTANT_SENTINEL, text)
        self.assertIn(
            "Reply exactly with the same marker, replacing the final word USER with ASSISTANT.",
            text,
        )
        self.assertIn("does not export ordinary conversation text", text)
        self.assertIn("does not export DOM `id` values", text)
        self.assertIn("does not make network requests", text)
        self.assertIn("If the live page exposes no sufficiently stable", text)

    def test_roadmap_tracks_completed_release_and_deepseek_issue(self):
        text = ROADMAP.read_text(encoding="utf-8")
        self.assertIn(
            "- [x] Publish the first tagged alpha with checksums / trusted publishing (#18)",
            text,
        )
        self.assertIn("- [ ] DeepSeek chat adapter (#58)", text)


if __name__ == "__main__":
    unittest.main()
