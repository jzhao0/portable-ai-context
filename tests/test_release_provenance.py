from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.verify_release_subjects import (
    SubjectVerificationError,
    verify_subjects,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
ROADMAP = ROOT / "ROADMAP.md"
ATTEST_SHA = "508db95dd578ae2727ebd6217d5ba78e4fbda05d"


class ReleaseSubjectVerificationTests(unittest.TestCase):
    def _write_valid_subjects(self, root: Path, version: str = "0.1.0a9") -> tuple[Path, Path, Path]:
        dist = root / "dist"
        dist.mkdir(parents=True)
        wheel = dist / f"portable_ai_context-{version}-py3-none-any.whl"
        sdist = dist / f"portable_ai_context-{version}.tar.gz"
        checksums = root / "SHA256SUMS"
        wheel.write_bytes(b"synthetic wheel bytes")
        sdist.write_bytes(b"synthetic sdist bytes")
        checksums.write_text(
            f"{hashlib.sha256(wheel.read_bytes()).hexdigest()}  {wheel.name}\n"
            f"{hashlib.sha256(sdist.read_bytes()).hexdigest()}  {sdist.name}\n",
            encoding="utf-8",
        )
        return wheel, sdist, checksums

    def test_exact_subject_set_and_checksums_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wheel, sdist, _ = self._write_valid_subjects(root)
            report = verify_subjects(version="0.1.0a9", artifacts_dir=root)
        self.assertTrue(report["ok"])
        self.assertEqual(report["checksum_entries"], 2)
        self.assertEqual(report["wheel_sha256"], hashlib.sha256(b"synthetic wheel bytes").hexdigest())
        self.assertEqual(report["sdist_sha256"], hashlib.sha256(b"synthetic sdist bytes").hexdigest())
        self.assertEqual(
            report["subjects"],
            [wheel.name, sdist.name, "SHA256SUMS"],
        )

    def test_extra_subject_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_valid_subjects(root)
            (root / "unexpected.txt").write_text("no", encoding="utf-8")
            with self.assertRaisesRegex(
                SubjectVerificationError,
                "exact expected file set",
            ):
                verify_subjects(version="0.1.0a9", artifacts_dir=root)

    def test_checksum_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wheel, _, _ = self._write_valid_subjects(root)
            wheel.write_bytes(b"tampered wheel")
            with self.assertRaisesRegex(
                SubjectVerificationError,
                "wheel SHA256 does not match",
            ):
                verify_subjects(version="0.1.0a9", artifacts_dir=root)

    def test_invalid_release_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_valid_subjects(root)
            with self.assertRaisesRegex(
                SubjectVerificationError,
                "alpha convention",
            ):
                verify_subjects(version="0.1.0", artifacts_dir=root)


class ReleaseProvenanceWorkflowContractTests(unittest.TestCase):
    def _workflow_text(self) -> str:
        return WORKFLOW.read_text(encoding="utf-8")

    def _attest_job(self) -> str:
        text = self._workflow_text()
        self.assertIn("\n  attest-published:\n", text)
        self.assertIn("\n  github-release:\n", text)
        return text.split("\n  attest-published:\n", 1)[1].split("\n  github-release:\n", 1)[0]

    def test_attestation_job_is_publish_only_and_ordered_after_live_pypi_verification(self):
        job = self._attest_job()
        self.assertIn("if: ${{ inputs.mode == 'publish' }}", job)
        self.assertIn("needs: [build, verify-published]", job)
        self.assertIn("Require release tag to still point to the built commit before attestation", job)
        self.assertIn("Download original build artifacts and checksums for attestation", job)
        self.assertIn("Recheck exact release subjects and local checksums before attestation", job)
        self.assertNotIn("python -m build", job)
        self.assertNotIn("actions/upload-artifact", job)
        self.assertNotIn("pypi-publish", job)

    def test_attestation_permissions_and_storage_record_scope_are_minimal(self):
        job = self._attest_job()
        self.assertIn("contents: read", job)
        self.assertIn("id-token: write", job)
        self.assertIn("attestations: write", job)
        self.assertNotIn("contents: write", job)
        self.assertNotIn("artifact-metadata: write", job)
        self.assertIn("create-storage-record: false", job)

    def test_attest_action_is_full_sha_pinned_and_subjects_are_exact(self):
        job = self._attest_job()
        self.assertIn(f"uses: actions/attest@{ATTEST_SHA} # v4.2.1", job)
        self.assertNotIn("actions/attest@v4", job)
        self.assertIn(
            "release-artifacts/dist/portable_ai_context-${{ needs.build.outputs.version }}-py3-none-any.whl",
            job,
        )
        self.assertIn(
            "release-artifacts/dist/portable_ai_context-${{ needs.build.outputs.version }}.tar.gz",
            job,
        )
        self.assertIn("release-artifacts/SHA256SUMS", job)
        self.assertIn("python tools/verify_release_subjects.py", job)

    def test_every_attested_subject_is_verified_against_repository(self):
        job = self._attest_job()
        self.assertEqual(job.count("gh attestation verify "), 3)
        self.assertEqual(job.count('--repo "$GITHUB_REPOSITORY"'), 3)
        self.assertIn("GH_TOKEN: ${{ github.token }}", job)

    def test_github_release_is_gated_on_attestation(self):
        text = self._workflow_text()
        release_job = text.split("\n  github-release:\n", 1)[1]
        self.assertIn("if: ${{ inputs.mode == 'publish' }}", release_job)
        self.assertIn("needs: [build, verify-published, attest-published]", release_job)
        self.assertIn("after PyPI and provenance verification", release_job)

    def test_dry_run_description_and_v1_roadmap_do_not_overclaim(self):
        text = self._workflow_text()
        self.assertIn(
            "dry-run builds/verifies only; publish enables PyPI + attestation + GitHub Release jobs",
            text,
        )
        roadmap = ROADMAP.read_text(encoding="utf-8")
        self.assertIn("- [ ] Signed releases / checksums", roadmap)


if __name__ == "__main__":
    unittest.main()
