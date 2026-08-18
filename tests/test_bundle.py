import json
import tempfile
from pathlib import Path
import unittest
import zipfile

from portable_ai_context.exporters import write_bundle
from _helpers import sample_conversation


class BundleTests(unittest.TestCase):
    def test_bundle_contains_expected_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "project.aicb"
            write_bundle(sample_conversation(), output)
            with zipfile.ZipFile(output) as z:
                names = set(z.namelist())
                self.assertEqual(
                    names,
                    {"manifest.json", "conversation.jsonl", "integrity.json", "privacy.json"},
                )
                manifest = json.loads(z.read("manifest.json"))
                self.assertEqual(manifest["schema_version"], "0.1-alpha")
                self.assertEqual(manifest["conversation"]["message_count"], 4)


if __name__ == "__main__":
    unittest.main()
