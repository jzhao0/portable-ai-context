from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from tools.public_surface_inventory import build_inventory


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "public_surface_0_1_alpha.json"
GOLDEN_SHA256 = "7d38a019a6bd850cc9c97d5e5600bb44aa24fcf8fe6e2605d80a2163173377bb"


class PublicSurfaceInventoryTests(unittest.TestCase):
    def test_inventory_fixture_bytes_are_pinned_and_lf_stable(self):
        raw = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), GOLDEN_SHA256)
        self.assertNotIn(b"\r\n", raw)

        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn(
            "tests/fixtures/public_surface_0_1_alpha.json text eol=lf",
            attributes,
        )

    def test_current_semantic_surface_matches_committed_inventory(self):
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        first = build_inventory()
        second = build_inventory()
        self.assertEqual(first, second)
        self.assertEqual(first, expected)

    def test_package_surface_records_installed_user_entry_points(self):
        inventory = build_inventory()
        package = inventory["package"]
        self.assertEqual(package["distribution_name"], "portable-ai-context")
        self.assertEqual(package["requires_python"], ">=3.10")
        self.assertEqual(package["optional_extras"], ["mcp", "tokenizers"])
        self.assertEqual(
            package["console_scripts"],
            {"paic": "portable_ai_context.cli:main"},
        )

    def test_python_api_exports_are_explicitly_inventoried(self):
        inventory = build_inventory()["python_api"]
        self.assertEqual(
            inventory["portable_ai_context"],
            ["Conversation", "Message", "SnapshotInfo", "SourceInfo"],
        )
        self.assertIn("compile_migration", inventory["portable_ai_context.compiler"])
        self.assertIn("ProviderNativeTokenCounter", inventory["portable_ai_context.compiler"])
        self.assertIn("register_backend", inventory["portable_ai_context.compiler"])
        self.assertEqual(
            inventory["portable_ai_context.compiler"],
            sorted(inventory["portable_ai_context.compiler"]),
        )

    def test_cli_inventory_contains_current_commands_and_semantic_options(self):
        cli = build_inventory()["cli"]
        self.assertEqual(cli["program"], "paic")
        self.assertEqual(cli["version_option_strings"], ["--version"])
        self.assertEqual(
            set(cli["subcommands"]),
            {
                "inspect",
                "verify",
                "conform",
                "smoke",
                "extract",
                "redact",
                "bundle",
                "checkpoint",
                "compile",
                "mcp",
            },
        )

        compile_options = {
            option["dest"]: option
            for option in cli["subcommands"]["compile"]["options"]
        }
        self.assertEqual(
            compile_options["token_counter"]["choices"],
            ["character", "tiktoken", "provider-native"],
        )
        self.assertEqual(compile_options["token_counter"]["default"], "character")
        self.assertTrue(compile_options["map_model"]["required"])
        self.assertTrue(compile_options["final_model"]["required"])
        self.assertEqual(compile_options["timeout"]["type"], "_positive_int")
        self.assertEqual(compile_options["timeout"]["default"], 300)

        mcp_options = {
            option["dest"]: option for option in cli["subcommands"]["mcp"]["options"]
        }
        self.assertEqual(set(mcp_options), {"root"})
        self.assertTrue(mcp_options["root"]["required"])

    def test_inventory_excludes_help_text_callable_reprs_and_environment_contents(self):
        serialized = json.dumps(build_inventory(), sort_keys=True)
        for forbidden_key in (
            '"help"',
            '"usage"',
            '"description"',
            '"epilog"',
        ):
            self.assertNotIn(forbidden_key, serialized)
        self.assertNotIn("<function", serialized)
        self.assertNotIn(" at 0x", serialized)
        self.assertNotIn("os.environ", serialized)
        self.assertNotIn("PRIVATE_", serialized)


if __name__ == "__main__":
    unittest.main()
