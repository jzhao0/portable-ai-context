import unittest
from unittest.mock import patch
import urllib.error

from portable_ai_context.adapters import chatgpt_share
from portable_ai_context.errors import ParseError


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

    @patch.object(chatgpt_share, "_fetch_browser")
    @patch.object(chatgpt_share, "_fetch_http")
    def test_403_falls_back_to_browser(self, fetch_http, fetch_browser):
        fetch_http.side_effect = urllib.error.HTTPError(FULL, 403, "Forbidden", None, None)
        fetch_browser.return_value = "browser html"
        self.assertEqual(chatgpt_share.fetch(FULL), "browser html")
        fetch_browser.assert_called_once_with(FULL)

    @patch.object(chatgpt_share, "_fetch_browser")
    @patch.object(chatgpt_share, "_fetch_http")
    def test_failure_message_distinguishes_http_and_browser_layers(self, fetch_http, fetch_browser):
        fetch_http.side_effect = urllib.error.URLError("offline")
        fetch_browser.side_effect = ParseError("no browser succeeded")
        with self.assertRaisesRegex(ParseError, "direct HTTP transport failed: URLError"):
            chatgpt_share.fetch(FULL)


if __name__ == "__main__":
    unittest.main()
