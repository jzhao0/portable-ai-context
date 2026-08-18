import tempfile
from pathlib import Path
import unittest

from portable_ai_context.adapters.registry import load_conversation
from _helpers import synthetic_chatgpt_html


class ChatGPTHTMLTests(unittest.TestCase):
    def test_synthetic_share_stream(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "share.html"
            path.write_text(synthetic_chatgpt_html(), encoding="utf-8")
            conv = load_conversation(str(path))
            self.assertEqual(conv.title, "Synthetic Share")
            self.assertEqual(len(conv.messages), 2)
            self.assertEqual(conv.messages[0].text, "Hello from user")
            self.assertEqual(conv.messages[1].text, "Hello from assistant")
            self.assertEqual(conv.snapshot.updated_at, 200.0)


if __name__ == "__main__":
    unittest.main()
