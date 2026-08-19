import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from portable_ai_context.cli import main as cli_main


class CheckpointCliErrorTests(unittest.TestCase):
    def test_tight_estimator_envelope_failure_is_clean_and_writes_no_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.jsonl"
            source.write_text(
                json.dumps({"role": "user", "text": "safe synthetic question"})
                + "\n"
                + json.dumps({"role": "assistant", "text": "safe synthetic answer"})
                + "\n",
                encoding="utf-8",
            )
            output = root / "checkpoint-output"
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = cli_main(
                    [
                        "checkpoint",
                        str(source),
                        "-o",
                        str(output),
                        "--budget",
                        "512",
                        "--chars-per-token",
                        "0.1",
                    ]
                )

            error = stderr.getvalue()
            self.assertEqual(code, 2)
            self.assertIn("budget is too small for the fixed checkpoint envelope", error)
            self.assertNotIn("Traceback", error)
            self.assertFalse((output / "CHECKPOINT.md").exists())
            self.assertFalse((output / "checkpoint-report.json").exists())


if __name__ == "__main__":
    unittest.main()
