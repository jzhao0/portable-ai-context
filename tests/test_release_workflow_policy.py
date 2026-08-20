from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
FULL_SHA_USE_RE = re.compile(r"^\s*-?\s*uses:\s+[^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$", re.MULTILINE)


class ReleaseWorkflowPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def _job(self, name: str, next_name: str | None = None) -> str:
        start = self.text.index(f"  {name}:")
        if next_name is None:
            return self.text[start:]
        end = self.text.index(f"\n  {next_name}:", start)
        return self.text[start:end]

    def test_release_is_manual_and_defaults_to_dry_run(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertNotIn("push:\n    tags:", self.text)
        self.assertIn("default: dry-run", self.text)
        self.assertIn("inputs.mode == 'publish'", self.text)

    def test_oidc_permissions_are_scoped_to_publish_and_attestation_jobs(self):
        self.assertEqual(self.text.count("id-token: write"), 2)
        self.assertIn("environment:\n      name: pypi", self.text)
        self.assertNotIn("PYPI_TOKEN", self.text)
        self.assertNotIn("password:", self.text)

        publish_job = self._job("pypi-publish", "verify-published")
        self.assertIn("permissions:\n      id-token: write", publish_job)
        self.assertNotIn("attestations: write", publish_job)

        attest_job = self._job("attest-published", "github-release")
        self.assertIn("contents: read", attest_job)
        self.assertIn("id-token: write", attest_job)
        self.assertIn("attestations: write", attest_job)

    def test_all_external_release_actions_are_pinned_to_full_shas(self):
        use_lines = [line.strip() for line in self.text.splitlines() if "uses:" in line]
        self.assertGreater(len(use_lines), 0)
        matches = FULL_SHA_USE_RE.findall(self.text)
        self.assertEqual(len(matches), len(use_lines), use_lines)
        self.assertNotRegex(self.text, r"uses:\s+[^\s]+@(v\d+|release/|main|master)\b")

    def test_publish_job_has_only_pinned_artifact_download_and_pypi_action(self):
        publish_job = self._job("pypi-publish", "verify-published")
        self.assertIn("needs: [build, prepublish-tag-check]", publish_job)
        self.assertIn(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1",
            publish_job,
        )
        self.assertIn(
            "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33 # v1.14.2",
            publish_job,
        )
        self.assertNotIn("actions/checkout", publish_job)
        self.assertNotIn("run:", publish_job)

    def test_checkout_credentials_are_not_persisted(self):
        self.assertEqual(self.text.count("persist-credentials: false"), 3)

    def test_tagged_commit_must_be_in_main_history(self):
        self.assertIn("git merge-base --is-ancestor HEAD origin/main", self.text)
        self.assertIn('ref: ${{ inputs.release_tag }}', self.text)

    def test_tag_identity_is_rechecked_before_after_publication_and_before_release(self):
        self.assertIn("prepublish-tag-check:", self.text)
        self.assertIn("Require release tag to still point to the built commit", self.text)
        self.assertIn(
            "Require release tag to still point to the built commit after publication",
            self.text,
        )
        self.assertIn(
            "Require release tag to still point to the built commit before attestation",
            self.text,
        )
        self.assertIn(
            "Require release tag to still point to the built commit before GitHub Release",
            self.text,
        )
        self.assertGreaterEqual(self.text.count('EXPECTED_COMMIT: ${{ needs.build.outputs.commit }}'), 4)

    def test_attestation_job_is_publish_only_and_uses_original_build_artifact(self):
        attest_job = self._job("attest-published", "github-release")
        self.assertIn("if: ${{ inputs.mode == 'publish' }}", attest_job)
        self.assertIn("needs: [build, verify-published]", attest_job)
        self.assertIn(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1",
            attest_job,
        )
        self.assertIn("name: release-dists-${{ inputs.release_tag }}", attest_job)
        self.assertNotIn("actions/checkout", attest_job)
        self.assertNotIn("python -m build", attest_job)
        self.assertNotIn("actions/upload-artifact", attest_job)
        self.assertNotIn("gh release create", attest_job)

    def test_attestation_revalidates_exact_artifact_set_checksums_and_tag(self):
        attest_job = self._job("attest-published", "github-release")
        self.assertIn("find release-artifacts -type f -printf '%P\\n' | sort", attest_job)
        self.assertIn('"SHA256SUMS" "dist/$WHEEL" "dist/$SDIST"', attest_job)
        self.assertIn('test "${#ACTUAL_FILES[@]}" -eq 3', attest_job)
        self.assertIn('test "$(wc -l < release-artifacts/SHA256SUMS)" -eq 2', attest_job)
        self.assertIn("awk 'NF != 2 || $1 !~ /^[0-9a-f]{64}$/ { exit 1 }'", attest_job)
        self.assertIn("sha256sum -c ../SHA256SUMS", attest_job)
        self.assertIn('ACTUAL_COMMIT="$(gh api "repos/$GITHUB_REPOSITORY/commits/$RELEASE_TAG" --jq .sha)"', attest_job)
        self.assertIn('test "$ACTUAL_COMMIT" = "$EXPECTED_COMMIT"', attest_job)

    def test_attest_action_and_independent_verification_are_locked(self):
        attest_job = self._job("attest-published", "github-release")
        self.assertIn(
            "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d # v4.2.1",
            attest_job,
        )
        self.assertIn("create-storage-record: false", attest_job)
        self.assertIn("release-artifacts/dist/*.whl", attest_job)
        self.assertIn("release-artifacts/dist/*.tar.gz", attest_job)
        self.assertIn("release-artifacts/SHA256SUMS", attest_job)
        self.assertEqual(attest_job.count('gh attestation verify "$subject" --repo "$GITHUB_REPOSITORY"'), 1)
        self.assertIn("for subject in", attest_job)

    def test_release_happens_after_pypi_verification_and_attestation(self):
        self.assertIn("Verify PyPI file hashes match tagged build", self.text)
        self.assertIn("Fresh install exact published version", self.text)
        release_job = self._job("github-release")
        self.assertIn("needs: [build, verify-published, attest-published]", release_job)
        self.assertIn("gh release create", release_job)
        self.assertIn("--verify-tag", release_job)


if __name__ == "__main__":
    unittest.main()
