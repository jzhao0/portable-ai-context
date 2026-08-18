import json
import tempfile
from pathlib import Path
import unittest

from portable_ai_context.adapters.registry import load_conversation


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
SCHEMA = ROOT / "schemas" / "browser-capture.schema.json"


class BrowserExtensionContractTests(unittest.TestCase):
    def test_manifest_uses_minimal_transient_permissions(self):
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(set(manifest.get("permissions", [])), {"activeTab", "scripting"})
        self.assertNotIn("host_permissions", manifest)
        self.assertNotIn("optional_host_permissions", manifest)

        forbidden = {
            "cookies",
            "webRequest",
            "webRequestBlocking",
            "tabs",
            "storage",
            "downloads",
            "debugger",
            "history",
            "clipboardRead",
            "clipboardWrite",
            "nativeMessaging",
        }
        self.assertTrue(forbidden.isdisjoint(manifest.get("permissions", [])))
        self.assertEqual(manifest["action"]["default_popup"], "popup.html")

    def test_popup_capture_has_no_network_cookie_or_whole_page_export_path(self):
        source = (EXTENSION / "popup.js").read_text(encoding="utf-8")
        for forbidden in [
            "document.cookie",
            "chrome.cookies",
            "chrome.webRequest",
            "XMLHttpRequest",
            "fetch(",
            "WebSocket(",
            "localStorage",
            "sessionStorage",
            ".outerHTML",
            ".innerHTML",
        ]:
            self.assertNotIn(forbidden, source)

        self.assertIn('"data-message-author-role"', source)
        self.assertIn('new Set(["user", "assistant"])', source)
        self.assertIn('"script"', source)
        self.assertIn('"style"', source)
        self.assertIn("textContent", source)
        self.assertIn("URL.createObjectURL", source)
        self.assertIn("application/x-ndjson", source)
        self.assertIn("paic-capture-${stamp}.jsonl", source)

    def test_intermediate_schema_is_allowlisted(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema_version"]["const"], "paic-browser-capture-1")
        self.assertEqual(schema["properties"]["messages"]["items"]["properties"]["role"]["enum"], ["user", "assistant"])
        for forbidden_field in ["url", "title", "cookies", "headers", "session", "account"]:
            self.assertNotIn(forbidden_field, schema["properties"])

    def test_exported_jsonl_shape_is_accepted_by_paic(self):
        content = "\n".join(
            [
                json.dumps({"role": "user", "text": "Browser capture question"}),
                json.dumps({"role": "assistant", "text": "Browser capture answer"}),
            ]
        ) + "\n"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "browser-capture.jsonl"
            path.write_text(content, encoding="utf-8")
            conv = load_conversation(str(path))

        self.assertEqual(
            [(m.role, m.text) for m in conv.messages],
            [
                ("user", "Browser capture question"),
                ("assistant", "Browser capture answer"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
