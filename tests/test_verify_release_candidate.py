from __future__ import annotations

import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from tools.verify_release_candidate import (
    CandidateVerificationError,
    main,
    verify_candidate,
)


VERSION = "0.1.0a9"
WHEEL = "portable_ai_context-0.1.0a9-py3-none-any.whl"
SDIST = "portable_ai_context-0.1.0a9.tar.gz"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class VerifyReleaseCandidateTests(unittest.TestCase):
    def _make_candidate(self, root: Path) -> tuple[Path, Path, dict[str, bytes]]:
        dist = root / "dist"
        dist.mkdir()
        payloads = {
            WHEEL: b"SYNTHETIC_WHEEL_BYTES_DO_NOT_ECHO",
            SDIST: b"SYNTHETIC_SDIST_BYTES_DO_NOT_ECHO",
        }
        for name, data in payloads.items():
            (dist / name).write_bytes(data)
        checksums = root / "SHA256SUMS"
        checksums.write_text(
            "".join(f"{_sha(payloads[name])}  {name}\n" for name in sorted(payloads)),
            encoding="utf-8",
        )
        return dist, checksums, payloads

    def test_valid_candidate_verifies_without_mutating_any_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist, checksums, payloads = self._make_candidate(root)
            before_files = {name: (dist / name).read_bytes() for name in payloads}
            before_checksums = checksums.read_bytes()

            report = verify_candidate(
                version=VERSION,
                artifacts_dir=dist,
                checksums=checksums,
            )

            after_files = {name: (dist / name).read_bytes() for name in payloads}
            after_checksums = checksums.read_bytes()

        self.assertTrue(report["ok"])
        self.assertTrue(report["read_only_verification"])
        self.assertEqual(report["version"], VERSION)
        self.assertEqual(report["wheel"], WHEEL)
        self.assertEqual(report["sdist"], SDIST)
        self.assertEqual(set(report["artifact_sha256"]), {WHEEL, SDIST})
        self.assertEqual(before_files, after_files)
        self.assertEqual(before_checksums, after_checksums)

    def test_missing_or_extra_distribution_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist, checksums, _ = self._make_candidate(root)
            (dist / WHEEL).unlink()
            with self.assertRaisesRegex(CandidateVerificationError, "exact expected"):
                verify_candidate(version=VERSION, artifacts_dir=dist, checksums=checksums)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist, checksums, _ = self._make_candidate(root)
            (dist / "extra.txt").write_text("PRIVATE_EXTRA_CONTENT", encoding="utf-8")
            with self.assertRaisesRegex(CandidateVerificationError, "exact expected") as caught:
                verify_candidate(version=VERSION, artifacts_dir=dist, checksums=checksums)
            self.assertNotIn("PRIVATE_EXTRA_CONTENT", str(caught.exception))

    def test_checksum_filename_set_must_be_exact(self):
        cases = {
            "missing": lambda lines: lines[:1],
            "extra": lambda lines: lines + [f"{'0' * 64}  extra.txt"],
        }
        for name, mutate in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                dist, checksums, _ = self._make_candidate(root)
                lines = checksums.read_text(encoding="utf-8").splitlines()
                checksums.write_text("\n".join(mutate(lines)) + "\n", encoding="utf-8")
                with self.assertRaises(CandidateVerificationError):
                    verify_candidate(version=VERSION, artifacts_dir=dist, checksums=checksums)

    def test_duplicate_checksum_filename_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist, checksums, payloads = self._make_candidate(root)
            checksums.write_text(
                f"{_sha(payloads[WHEEL])}  {WHEEL}\n"
                f"{_sha(payloads[WHEEL])}  {WHEEL}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CandidateVerificationError, "duplicate filename"):
                verify_candidate(version=VERSION, artifacts_dir=dist, checksums=checksums)

    def test_malformed_digest_and_unsafe_checksum_path_fail(self):
        unsafe_lines = [
            f"{'G' * 64}  {WHEEL}\n{'0' * 64}  {SDIST}\n",
            f"{'0' * 64}  ../{WHEEL}\n{'0' * 64}  {SDIST}\n",
            f"{'0' * 64}  nested/{WHEEL}\n{'0' * 64}  {SDIST}\n",
            f"{'0' * 64} *{WHEEL}\n{'0' * 64}  {SDIST}\n",
        ]
        for body in unsafe_lines:
            with self.subTest(body=body[:20]), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                dist, checksums, _ = self._make_candidate(root)
                checksums.write_text(body, encoding="utf-8")
                with self.assertRaisesRegex(CandidateVerificationError, "malformed entry"):
                    verify_candidate(version=VERSION, artifacts_dir=dist, checksums=checksums)

    def test_hash_mismatch_fails_without_echoing_artifact_body(self):
        private_body = b"PRIVATE_RELEASE_ARTIFACT_BODY_DO_NOT_ECHO"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dist, checksums, _ = self._make_candidate(root)
            (dist / WHEEL).write_bytes(private_body)
            with self.assertRaisesRegex(CandidateVerificationError, "SHA256 mismatch") as caught:
                verify_candidate(version=VERSION, artifacts_dir=dist, checksums=checksums)
        self.assertNotIn(private_body.decode("ascii"), str(caught.exception))

    def test_invalid_version_fails_before_filesystem_access(self):
        with self.assertRaisesRegex(CandidateVerificationError, "alpha convention"):
            verify_candidate(
                version="0.1.0a9/../../PRIVATE",
                artifacts_dir=Path("PRIVATE_ARTIFACT_DIRECTORY"),
                checksums=Path("PRIVATE_CHECKSUM_FILE"),
            )

    def test_cli_read_error_does_not_echo_private_local_path(self):
        private_root = Path("C:/Users/PRIVATE_USER/Secret Release Candidate")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = main(
                [
                    "--version",
                    VERSION,
                    "--artifacts-dir",
                    str(private_root / "dist"),
                    "--checksums",
                    str(private_root / "SHA256SUMS"),
                ]
            )
        error = stderr.getvalue()
        self.assertEqual(code, 2)
        self.assertNotIn("PRIVATE_USER", error)
        self.assertNotIn("Secret Release Candidate", error)


if __name__ == "__main__":
    unittest.main()
