import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import release_guard


class ReleaseGuardTests(unittest.TestCase):
    def test_current_repository_version_sources_agree(self):
        project_version = release_guard._project_version()
        self.assertEqual(release_guard._package_version(), project_version)
        self.assertIsNotNone(release_guard.TAG_RE.fullmatch(f"v{project_version}"))
        with mock.patch.object(release_guard, "_validate_tag", return_value="tagged-main-sha"):
            report = release_guard.validate_release(tag=f"v{project_version}", mode="dry-run")
        self.assertTrue(report["ok"])
        self.assertEqual(report["version"], project_version)
        self.assertEqual(report["commit"], "tagged-main-sha")

    def test_alpha_tag_must_match_project_version(self):
        with mock.patch.object(release_guard, "_git", return_value="abc123"):
            self.assertEqual(
                release_guard._validate_tag("v0.1.0a2", "0.1.0a2"),
                "abc123",
            )
            with self.assertRaisesRegex(release_guard.ReleaseGuardError, "tag/project version mismatch"):
                release_guard._validate_tag("v0.1.0a3", "0.1.0a2")

    def test_non_alpha_tag_is_rejected(self):
        with self.assertRaisesRegex(release_guard.ReleaseGuardError, "vX.Y.ZaN"):
            release_guard._validate_tag("0.1.0a2", "0.1.0a2")
        with self.assertRaisesRegex(release_guard.ReleaseGuardError, "vX.Y.ZaN"):
            release_guard._validate_tag("v0.1.0", "0.1.0a2")

    def test_tagged_commit_must_equal_head(self):
        def fake_git(*args):
            if args == ("rev-parse", "HEAD"):
                return "headsha"
            return "tagsha"

        with mock.patch.object(release_guard, "_git", side_effect=fake_git):
            with self.assertRaisesRegex(release_guard.ReleaseGuardError, "HEAD does not match"):
                release_guard._validate_tag("v0.1.0a2", "0.1.0a2")

    def test_exact_wheel_and_sdist_set_produces_checksums(self):
        version = "0.1.0a2"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wheel = root / "portable_ai_context-0.1.0a2-py3-none-any.whl"
            sdist = root / "portable_ai_context-0.1.0a2.tar.gz"
            wheel.write_bytes(b"wheel-bytes")
            sdist.write_bytes(b"sdist-bytes")
            output = root / "SHA256SUMS"

            digests = release_guard._write_checksums(root, output, version)

            self.assertEqual(
                digests[wheel.name], hashlib.sha256(b"wheel-bytes").hexdigest()
            )
            self.assertEqual(
                digests[sdist.name], hashlib.sha256(b"sdist-bytes").hexdigest()
            )
            text = output.read_text(encoding="utf-8")
            self.assertIn(wheel.name, text)
            self.assertIn(sdist.name, text)

    def test_unexpected_distribution_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "portable_ai_context-0.1.0a2-py3-none-any.whl").write_bytes(b"wheel")
            (root / "portable_ai_context-0.1.0a2.tar.gz").write_bytes(b"sdist")
            (root / "portable_ai_context-0.1.0a2-extra.whl").write_bytes(b"extra")
            with self.assertRaisesRegex(release_guard.ReleaseGuardError, "artifact"):
                release_guard._write_checksums(root, root / "SHA256SUMS", "0.1.0a2")

    def test_publish_mode_requires_released_changelog_heading(self):
        with mock.patch.object(Path, "read_text", return_value="# Changelog\n\n## 0.1.0a2 — Unreleased\n"):
            with self.assertRaisesRegex(release_guard.ReleaseGuardError, "Unreleased"):
                release_guard._validate_changelog("0.1.0a2", "publish")

    def test_dry_run_allows_unreleased_changelog_heading(self):
        with mock.patch.object(Path, "read_text", return_value="# Changelog\n\n## 0.1.0a2 — Unreleased\n"):
            release_guard._validate_changelog("0.1.0a2", "dry-run")

    def test_changelog_version_match_does_not_accept_longer_prefix(self):
        with mock.patch.object(Path, "read_text", return_value="# Changelog\n\n## 0.1.0a20 — Released\n"):
            with self.assertRaisesRegex(release_guard.ReleaseGuardError, "exactly one heading"):
                release_guard._validate_changelog("0.1.0a2", "dry-run")


if __name__ == "__main__":
    unittest.main()
