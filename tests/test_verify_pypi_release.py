from pathlib import Path
import tempfile
import unittest

from tools.verify_pypi_release import VerificationError, load_checksums, verify_payload


class VerifyPyPIReleaseTests(unittest.TestCase):
    def test_exact_release_file_hashes_pass(self):
        expected = {
            "portable_ai_context-0.1.0a2-py3-none-any.whl": "a" * 64,
            "portable_ai_context-0.1.0a2.tar.gz": "b" * 64,
        }
        payload = {
            "info": {"version": "0.1.0a2"},
            "urls": [
                {
                    "filename": "portable_ai_context-0.1.0a2-py3-none-any.whl",
                    "digests": {"sha256": "a" * 64},
                },
                {
                    "filename": "portable_ai_context-0.1.0a2.tar.gz",
                    "digests": {"sha256": "b" * 64},
                },
            ],
        }
        self.assertEqual(verify_payload(payload, expected, "0.1.0a2"), expected)

    def test_missing_or_extra_pypi_file_fails_closed(self):
        expected = {
            "portable_ai_context-0.1.0a2-py3-none-any.whl": "a" * 64,
            "portable_ai_context-0.1.0a2.tar.gz": "b" * 64,
        }
        payload = {
            "info": {"version": "0.1.0a2"},
            "urls": [
                {
                    "filename": "portable_ai_context-0.1.0a2-py3-none-any.whl",
                    "digests": {"sha256": "a" * 64},
                }
            ],
        }
        with self.assertRaisesRegex(VerificationError, "hash set mismatch"):
            verify_payload(payload, expected, "0.1.0a2")

    def test_wrong_hash_fails_closed(self):
        expected = {"portable_ai_context-0.1.0a2.tar.gz": "b" * 64}
        payload = {
            "info": {"version": "0.1.0a2"},
            "urls": [
                {
                    "filename": "portable_ai_context-0.1.0a2.tar.gz",
                    "digests": {"sha256": "c" * 64},
                }
            ],
        }
        with self.assertRaisesRegex(VerificationError, "hash set mismatch"):
            verify_payload(payload, expected, "0.1.0a2")

    def test_wrong_metadata_version_fails(self):
        with self.assertRaisesRegex(VerificationError, "metadata version"):
            verify_payload({"info": {"version": "0.1.0a3"}, "urls": []}, {}, "0.1.0a2")

    def test_checksum_file_parser_is_strict(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "SHA256SUMS"
            path.write_text(
                f"{'a' * 64}  portable_ai_context-0.1.0a2-py3-none-any.whl\n"
                f"{'b' * 64}  portable_ai_context-0.1.0a2.tar.gz\n",
                encoding="utf-8",
            )
            parsed = load_checksums(path)
        self.assertEqual(len(parsed), 2)


if __name__ == "__main__":
    unittest.main()
