import tempfile
from pathlib import Path
import unittest
from unittest import mock
import zlib

from portable_ai_context.adapters import load_conversation
from portable_ai_context.adapters import aicb
from portable_ai_context.errors import ParseError


class AICBRegistryFailCleanTests(unittest.TestCase):
    def _source_path(self, root: Path) -> Path:
        source = root / "private-project.aicb"
        source.write_bytes(b"placeholder")
        return source

    def test_oserror_is_wrapped_without_leaking_low_level_detail(self):
        private_detail = r"C:\\Users\\PRIVATE_USER\\secret-bundle.aicb"
        with tempfile.TemporaryDirectory() as td:
            source = self._source_path(Path(td))
            with mock.patch.object(aicb, "load", side_effect=OSError(private_detail)):
                with self.assertRaises(ParseError) as caught:
                    load_conversation(str(source))

        message = str(caught.exception)
        self.assertEqual(
            message,
            "AICB bundle contract violation: archive could not be read safely",
        )
        self.assertNotIn("PRIVATE_USER", message)

    def test_zlib_error_is_wrapped_without_leaking_low_level_detail(self):
        private_detail = "PRIVATE_COMPRESSED_PAYLOAD_DETAIL"
        with tempfile.TemporaryDirectory() as td:
            source = self._source_path(Path(td))
            with mock.patch.object(aicb, "load", side_effect=zlib.error(private_detail)):
                with self.assertRaises(ParseError) as caught:
                    load_conversation(str(source))

        message = str(caught.exception)
        self.assertEqual(
            message,
            "AICB bundle contract violation: archive could not be read safely",
        )
        self.assertNotIn(private_detail, message)


if __name__ == "__main__":
    unittest.main()
