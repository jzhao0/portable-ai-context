import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from pathlib import Path

from portable_ai_context.adapters import chatgpt_share
from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation, SourceInfo


SHARE_ID = "6a7efdf6-abcc-83e8-9a7f-b0013d633f46"
FULL = f"https://chatgpt.com/share/{SHARE_ID}"


class ChatGPTShareTests(unittest.TestCase):
    def test_normalize_common_share_inputs(self):
        cases = {
            FULL: FULL,
            f"chatgpt.com/share/{SHARE_ID}": FULL,
            f"www.chatgpt.com/share/{SHARE_ID}": f"https://www.chatgpt.com/share/{SHARE_ID}",
            f"/share/{SHARE_ID}": FULL,
            f"share/{SHARE_ID}": FULL,
            SHARE_ID: FULL,
            "/tmp/conversation.html": "/tmp/conversation.html",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(chatgpt_share.normalize_share_input(source), expected)

    def test_share_id_is_recognized_as_url_after_normalization(self):
        self.assertTrue(chatgpt_share.is_share_url(SHARE_ID))

    def test_macos_candidate_paths_cover_supported_browsers(self):
        paths = chatgpt_share._platform_browser_paths(
            "Darwin", {}, Path("/Users/test")
        )
        joined = "\n".join(paths)
        self.assertIn("Google Chrome.app", joined)
        self.assertIn("Microsoft Edge.app", joined)
        self.assertIn("Brave Browser.app", joined)
        self.assertIn("Chromium.app", joined)
        self.assertIn("/Users/test/Applications/", joined)

    def test_windows_candidate_paths_cover_supported_browsers(self):
        paths = chatgpt_share._platform_browser_paths(
            "Windows",
            {
                "PROGRAMFILES": r"C:\Program Files",
                "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
                "LOCALAPPDATA": r"C:\Users\test\AppData\Local",
            },
            Path("/unused"),
        )
        joined = "\n".join(paths)
        self.assertIn(r"Google\Chrome\Application\chrome.exe", joined)
        self.assertIn(r"Microsoft\Edge\Application\msedge.exe", joined)
        self.assertIn(r"BraveSoftware\Brave-Browser\Application\brave.exe", joined)
        self.assertIn(r"C:\Users\test\AppData\Local", joined)

    def test_linux_candidate_paths_cover_common_locations(self):
        paths = chatgpt_share._platform_browser_paths("Linux", {}, Path("/home/test"))
        self.assertIn("/usr/bin/google-chrome", paths)
        self.assertIn("/usr/bin/chromium", paths)
        self.assertIn("/snap/bin/chromium", paths)
        self.assertIn("/usr/bin/microsoft-edge", paths)
        self.assertIn("/usr/bin/brave-browser", paths)

    def test_browser_command_uses_isolated_profile(self):
        with tempfile.TemporaryDirectory(prefix="paic-test-") as profile:
            cmd = chatgpt_share._browser_command(
                "/browser", profile, "--headless=new", FULL
            )
            self.assertIn(f"--user-data-dir={profile}", cmd)
            self.assertIn("--disable-extensions", cmd)
            self.assertIn("--disable-sync", cmd)
            self.assertNotIn("--remote-debugging-port=9222", cmd)
            self.assertEqual(cmd[-1], FULL)

    @patch.object(chatgpt_share, "_fetch_http")
    def test_capture_reports_direct_http(self, fetch_http):
        fetch_http.return_value = "streamController.enqueue linear_conversation"
        html, method = chatgpt_share._capture(FULL)
        self.assertEqual(html, "streamController.enqueue linear_conversation")
        self.assertEqual(method, "direct_http")

    @patch.object(chatgpt_share, "_fetch_browser")
    @patch.object(chatgpt_share, "_fetch_http")
    def test_403_falls_back_to_browser(self, fetch_http, fetch_browser):
        fetch_http.side_effect = urllib.error.HTTPError(FULL, 403, "Forbidden", None, None)
        fetch_browser.return_value = "browser html"
        html, method = chatgpt_share._capture(FULL)
        self.assertEqual(html, "browser html")
        self.assertEqual(method, "browser_fallback")
        fetch_browser.assert_called_once_with(FULL)
        self.assertEqual(chatgpt_share.fetch(FULL), "browser html")

    @patch.object(chatgpt_share.chatgpt_html, "load")
    @patch.object(chatgpt_share, "_capture", return_value=("captured html", "direct_http"))
    def test_load_records_capture_method(self, _capture, html_load):
        html_load.return_value = Conversation(
            title="test",
            messages=[],
            source=SourceInfo(kind="chatgpt_html"),
        )
        conv = chatgpt_share.load(FULL)
        self.assertEqual(conv.source.kind, "chatgpt_share_url")
        self.assertEqual(conv.source.metadata["capture_method"], "direct_http")

    @patch.object(chatgpt_share, "_fetch_browser")
    @patch.object(chatgpt_share, "_fetch_http")
    def test_failure_message_distinguishes_http_and_browser_layers(self, fetch_http, fetch_browser):
        fetch_http.side_effect = urllib.error.URLError("offline")
        fetch_browser.side_effect = ParseError("no browser succeeded")
        with self.assertRaisesRegex(ParseError, "direct HTTP transport failed: URLError"):
            chatgpt_share.fetch(FULL)

    @patch.object(chatgpt_share, "_browser_candidates", return_value=[])
    def test_browser_failure_explains_override(self, _candidates):
        with self.assertRaisesRegex(ParseError, "PAIC_BROWSER"):
            chatgpt_share._fetch_browser(FULL)


if __name__ == "__main__":
    unittest.main()
