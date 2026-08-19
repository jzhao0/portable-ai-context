from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

try:
    import tomllib
except ImportError:  # Python 3.10
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "mcp"
GENERIC_ROOT = "/ABSOLUTE/PATH/TO/WORKSPACE"
EXPECTED_ARGS = ["mcp", "--root"]


class MCPHandoffRecipeTests(unittest.TestCase):
    def _read(self, name: str) -> str:
        return (EXAMPLES / name).read_text(encoding="utf-8")

    def _assert_example_text_is_safe(self, text: str) -> None:
        lowered = text.lower()
        forbidden = (
            "http://",
            "https://",
            "api_key",
            "apikey",
            "bearer",
            "authorization",
            "client_secret",
            "access_token",
            "cmd /c",
            "powershell",
            "bash -c",
            "sh -c",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, lowered)

    def _assert_stdio_entry(self, entry: dict, *, expected_root: str) -> None:
        self.assertEqual(entry.get("type"), "stdio")
        self.assertEqual(entry.get("command"), "paic")
        self.assertEqual(entry.get("args"), [*EXPECTED_ARGS, expected_root])
        self.assertEqual(set(entry), {"type", "command", "args"})

    def test_examples_are_inert_and_no_active_project_configs_are_committed(self):
        expected_examples = {
            "codex.config.toml.example",
            "claude.mcp.json.example",
            "cursor.mcp.json.example",
        }
        self.assertEqual({path.name for path in EXAMPLES.iterdir() if path.is_file()}, expected_examples)
        for path in (
            ROOT / ".mcp.json",
            ROOT / ".cursor" / "mcp.json",
            ROOT / ".codex" / "config.toml",
        ):
            with self.subTest(path=path.as_posix()):
                self.assertFalse(path.exists())

    def test_codex_toml_recipe_is_minimal_stdio_paic_command(self):
        text = self._read("codex.config.toml.example")
        self._assert_example_text_is_safe(text)
        meaningful = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(
            meaningful,
            [
                "[mcp_servers.paic]",
                'command = "paic"',
                f'args = ["mcp", "--root", "{GENERIC_ROOT}"]',
            ],
        )
        if tomllib is not None:
            parsed = tomllib.loads(text)
            self.assertEqual(
                parsed,
                {
                    "mcp_servers": {
                        "paic": {
                            "command": "paic",
                            "args": [*EXPECTED_ARGS, GENERIC_ROOT],
                        }
                    }
                },
            )
        else:
            self.assertEqual(sys.version_info[:2], (3, 10))

    def test_claude_project_json_recipe_is_minimal_stdio_paic_command(self):
        text = self._read("claude.mcp.json.example")
        self._assert_example_text_is_safe(text)
        parsed = json.loads(text)
        self.assertEqual(set(parsed), {"mcpServers"})
        self.assertEqual(set(parsed["mcpServers"]), {"paic"})
        self._assert_stdio_entry(parsed["mcpServers"]["paic"], expected_root=GENERIC_ROOT)

    def test_cursor_project_json_recipe_uses_workspace_folder(self):
        text = self._read("cursor.mcp.json.example")
        self._assert_example_text_is_safe(text)
        parsed = json.loads(text)
        self.assertEqual(set(parsed), {"mcpServers"})
        self.assertEqual(set(parsed["mcpServers"]), {"paic"})
        self._assert_stdio_entry(
            parsed["mcpServers"]["paic"],
            expected_root="${workspaceFolder}",
        )

    def test_generic_absolute_placeholder_contains_no_machine_identity(self):
        self.assertEqual(GENERIC_ROOT, "/ABSOLUTE/PATH/TO/WORKSPACE")
        lowered = GENERIC_ROOT.lower()
        for marker in ("/users/", "/home/", "\\users\\", "jzhao0", "junjie"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, lowered)


if __name__ == "__main__":
    unittest.main()
