from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


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

    def test_publish_job_has_only_artifact_download_and_pypi_action(self):
        start = self.text.index("  pypi-publish:")
        end = self.text.index("\n  verify-published:", start)
        publish_job = self.text[start:end]
        self.assertIn("actions/download-artifact@v4", publish_job)
        self.assertIn("pypa/gh-action-pypi-publish@v1.14.2", publish_job)
        self.assertNotIn("actions/checkout", publish_job)
        self.assertNotIn("run:", publish_job)

    def test_tagged_commit_must_be_in_main_history(self):
        self.assertIn("git merge-base --is-ancestor HEAD origin/main", self.text)
        self.assertIn('ref: ${{ inputs.release_tag }}', self.text)

    def test_release_happens_after_pypi_hash_and_install_verification(self):
        self.assertIn("Verify PyPI file hashes match tagged build", self.text)
        self.assertIn("Fresh install exact published version", self.text)
        self.assertIn("needs: [build, verify-published]", self.text)
        self.assertIn("gh release create", self.text)
        self.assertIn("--verify-tag", self.text)


if __name__ == "__main__":
    unittest.main()
