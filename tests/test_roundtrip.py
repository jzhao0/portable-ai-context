import tempfile
from pathlib import Path
import unittest

from portable_ai_context.adapters.registry import load_conversation
from portable_ai_context.exporters import write_standard
from _helpers import sample_conversation


class RoundTripTests(unittest.TestCase):
    def test_clean_html_txt_jsonl_roundtrip(self):
        conv = sample_conversation()
        with tempfile.TemporaryDirectory() as td:
            paths = write_standard(conv, td)
            for key in ["clean_html", "compact_txt", "jsonl"]:
                loaded = load_conversation(str(paths[key]))
                self.assertEqual([m.text for m in loaded.messages], [m.text for m in conv.messages])
                self.assertEqual([m.role for m in loaded.messages], [m.role for m in conv.messages])


if __name__ == "__main__":
    unittest.main()
