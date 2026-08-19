from pathlib import Path
import tempfile
import unittest

from portable_ai_context.mcp_workspace import (
    MCP_ALLOWED_SOURCE_SUFFIXES,
    MCP_ARTIFACT_DIRNAME,
    MCPWorkspace,
    MCPWorkspaceError,
)


PRIVATE_PATH_TOKEN = "PRIVATE_PATH_TOKEN"


class MCPWorkspaceTests(unittest.TestCase):
    def test_valid_nested_source_resolves_within_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested = root / "nested"
            nested.mkdir()
            source = nested / "conversation.jsonl"
            source.write_text('{"role":"user","text":"hi"}\n', encoding="utf-8")

            workspace = MCPWorkspace.from_root(root)
            resolved = workspace.resolve_source("nested/conversation.jsonl")

            self.assertEqual(resolved, source.resolve())

    def test_public_source_suffix_contract_matches_local_registry(self):
        self.assertEqual(
            MCP_ALLOWED_SOURCE_SUFFIXES,
            frozenset({".aicb", ".jsonl", ".ndjson", ".json", ".txt", ".html", ".htm"}),
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ndjson = root / "conversation.ndjson"
            htm = root / "conversation.htm"
            ndjson.write_text('{"role":"user","text":"hi"}\n', encoding="utf-8")
            htm.write_text("<html></html>", encoding="utf-8")
            workspace = MCPWorkspace.from_root(root)

            self.assertEqual(workspace.resolve_source("conversation.ndjson"), ndjson.resolve())
            self.assertEqual(workspace.resolve_source("conversation.htm"), htm.resolve())

    def test_rejects_unsafe_relative_path_forms_without_echo(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = MCPWorkspace.from_root(td)
            unsafe = (
                f"../{PRIVATE_PATH_TOKEN}.jsonl",
                f"/{PRIVATE_PATH_TOKEN}.jsonl",
                f"C:/{PRIVATE_PATH_TOKEN}.jsonl",
                f"nested\\{PRIVATE_PATH_TOKEN}.jsonl",
                f"nested//{PRIVATE_PATH_TOKEN}.jsonl",
                f"nested/./{PRIVATE_PATH_TOKEN}.jsonl",
                f"nested/../{PRIVATE_PATH_TOKEN}.jsonl",
                f"nested/{PRIVATE_PATH_TOKEN}\n.jsonl",
            )
            for value in unsafe:
                with self.subTest(value=value):
                    with self.assertRaises(MCPWorkspaceError) as caught:
                        workspace.resolve_source(value)
                    self.assertNotIn(PRIVATE_PATH_TOKEN, str(caught.exception))

    def test_rejects_unsupported_suffix_and_oversized_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "private.bin").write_bytes(b"x")
            (root / "large.jsonl").write_bytes(b"12345")
            workspace = MCPWorkspace.from_root(root, max_source_bytes=4)

            with self.assertRaisesRegex(MCPWorkspaceError, "source type is not supported"):
                workspace.resolve_source("private.bin")
            with self.assertRaisesRegex(MCPWorkspaceError, "exceeds the configured size limit"):
                workspace.resolve_source("large.jsonl")

    def test_rejects_directory_and_missing_source_without_echo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "looks.jsonl").mkdir()
            workspace = MCPWorkspace.from_root(root)

            with self.assertRaises(MCPWorkspaceError) as directory_error:
                workspace.resolve_source("looks.jsonl")
            with self.assertRaises(MCPWorkspaceError) as missing_error:
                workspace.resolve_source(f"{PRIVATE_PATH_TOKEN}.jsonl")

            self.assertNotIn(PRIVATE_PATH_TOKEN, str(missing_error.exception))
            self.assertIn("unavailable", str(directory_error.exception))

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as root_td, tempfile.TemporaryDirectory() as outside_td:
            root = Path(root_td)
            outside = Path(outside_td)
            secret = outside / f"{PRIVATE_PATH_TOKEN}.jsonl"
            secret.write_text('{"role":"user","text":"secret"}\n', encoding="utf-8")
            link = root / "linked.jsonl"
            try:
                link.symlink_to(secret)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this platform/runtime")

            workspace = MCPWorkspace.from_root(root)
            with self.assertRaises(MCPWorkspaceError) as caught:
                workspace.resolve_source("linked.jsonl")
            self.assertNotIn(PRIVATE_PATH_TOKEN, str(caught.exception))
            self.assertIn("escapes", str(caught.exception))

    def test_artifact_directories_are_unique_and_root_relative(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            workspace = MCPWorkspace.from_root(root)

            first = workspace.create_artifact_directory("checkpoints")
            second = workspace.create_artifact_directory("checkpoints")
            redaction = workspace.create_artifact_directory("redactions")

            self.assertNotEqual(first, second)
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            self.assertTrue(redaction.is_dir())
            for path in (first, second, redaction):
                relative = workspace.relative_display(path)
                self.assertTrue(relative.startswith(f"{MCP_ARTIFACT_DIRNAME}/"))
                self.assertFalse(Path(relative).is_absolute())

    def test_artifact_root_symlink_or_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside_td:
            root = Path(td)
            artifact = root / MCP_ARTIFACT_DIRNAME
            workspace = MCPWorkspace.from_root(root)

            artifact.write_text("not a directory", encoding="utf-8")
            with self.assertRaisesRegex(MCPWorkspaceError, "artifact area is unavailable"):
                workspace.create_artifact_directory("checkpoints")
            artifact.unlink()

            try:
                artifact.symlink_to(Path(outside_td), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable on this platform/runtime")
            with self.assertRaisesRegex(MCPWorkspaceError, "artifact area is unavailable"):
                workspace.create_artifact_directory("redactions")

    def test_artifact_category_is_internal_only(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = MCPWorkspace.from_root(td)
            with self.assertRaisesRegex(ValueError, "unsupported MCP artifact category"):
                workspace.create_artifact_directory("PRIVATE_CATEGORY")

    def test_unavailable_root_errors_are_content_safe(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / PRIVATE_PATH_TOKEN
            with self.assertRaises(MCPWorkspaceError) as caught:
                MCPWorkspace.from_root(missing)
            self.assertNotIn(PRIVATE_PATH_TOKEN, str(caught.exception))

        with self.assertRaisesRegex(MCPWorkspaceError, "workspace root is unavailable"):
            MCPWorkspace.from_root(object())


if __name__ == "__main__":
    unittest.main()
