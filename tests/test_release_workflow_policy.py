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

    def test_release_is_manual_and_defaults_to_dry_run(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertNotIn("push:\n    tags:", self.text)
        self.assertIn("default: dry-run", self.text)
        self.assertIn("inputs.mode == 'publish'", self.text)

    def test_oidc_permission_is_scoped_to_publish_job(self):
        self.assertEqual(self.text.count("id-token: write"), 1)
        self.assertIn("environment:\n      name: pypi", self.text)
        self.assertNotIn("PYPI_TOKEN", self.text)
        self.assertNotIn("password:", self.text)

    def test_all_external_release_actions_are_pinned_to_full_shas(self):
        use_lines = [line.strip() for line in self.text.splitlines() if "uses:" in line]
        self.assertGreater(len(use_lines), 0)
        matches = FULL_SHA_USE_RE.findall(self.text)
        self.assertEqual(len(matches), len(use_lines), use_lines)
        self.assertNotRegex(self.text, r"uses:\s+[^\s]+@(v\d+|release/|main|master)\b")

    def test_publish_job_has_only_pinned_artifact_download_and_pypi_action(self):
        start = self.text.index("  pypi-publish:")
        end = self.text.index("\n  verify-published:", start)
        publish_job = self.text[start:end]
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

    def test_tag_identity_is_rechecked_before_and_after_publication(self):
        self.assertIn("prepublish-tag-check:", self.text)
        self.assertIn("Require release tag to still point to the built commit", self.text)
        self.assertIn(
            "Require release tag to still point to the built commit after publication",
            self.text,
        )
        self.assertIn(
            "Require release tag to still point to the built commit before GitHub Release",
            self.text,
        )
        self.assertGreaterEqual(self.text.count('ref: ${{ needs.build.outputs.commit }}'), 2)
        self.assertGreaterEqual(self.text.count('EXPECTED_COMMIT: ${{ needs.build.outputs.commit }}'), 3)

    def test_release_happens_after_pypi_hash_and_install_verification(self):
        self.assertIn("Verify PyPI file hashes match tagged build", self.text)
        self.assertIn("Fresh install exact published version", self.text)
        self.assertIn("needs: [build, verify-published]", self.text)
        self.assertIn("gh release create", self.text)
        self.assertIn("--verify-tag", self.text)


if __name__ == "__main__":
    unittest.main()
