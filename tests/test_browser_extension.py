import json
import tempfile
from pathlib import Path
import unittest

from portable_ai_context.adapters.registry import load_conversation


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
SCHEMA = ROOT / "schemas" / "browser-capture.schema.json"
FIREFOX_PACKAGE_SMOKE = ROOT / "tools" / "firefox_extension_package_smoke.py"
EXPECTED_GECKO_ID = "portable-ai-context-capture@jzhao0.github.io"


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

    def test_firefox_manifest_metadata_is_reviewed_and_does_not_claim_runtime_baseline(self):
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        settings = manifest.get("browser_specific_settings")
        self.assertIsInstance(settings, dict)
        self.assertEqual(set(settings), {"gecko"})
        gecko = settings["gecko"]
        self.assertEqual(gecko.get("id"), EXPECTED_GECKO_ID)
        self.assertEqual(
            gecko.get("data_collection_permissions"),
            {"required": ["none"]},
        )
        self.assertNotIn("strict_min_version", gecko)
        self.assertNotIn("strict_max_version", gecko)
        self.assertNotIn("update_url", gecko)

    def test_popup_uses_narrow_cross_browser_promise_namespace_selector(self):
        source = (EXTENSION / "popup.js").read_text(encoding="utf-8")
        self.assertIn(
            'const extensionApi = typeof browser !== "undefined" ? browser : chrome;',
            source,
        )
        self.assertIn("await extensionApi.tabs.query", source)
        self.assertIn("await extensionApi.scripting.executeScript", source)
        self.assertNotIn("await chrome.tabs.query", source)
        self.assertNotIn("await chrome.scripting.executeScript", source)
        self.assertNotIn("webextension-polyfill", source.lower())

    def test_popup_capture_has_no_network_cookie_storage_or_whole_page_export_path(self):
        source = (EXTENSION / "popup.js").read_text(encoding="utf-8")
        for forbidden in [
            "document.cookie",
            "chrome.cookies",
            "chrome.webRequest",
            "chrome.storage",
            "browser.cookies",
            "browser.webRequest",
            "browser.storage",
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
        self.assertIn(
            ".map((message) => JSON.stringify({ role: message.role, text: message.text }))",
            source,
        )

    def test_firefox_package_smoke_rechecks_security_shape(self):
        source = FIREFOX_PACKAGE_SMOKE.read_text(encoding="utf-8")
        for marker in [
            'EXPECTED_PERMISSIONS = {"activeTab", "scripting"}',
            f'EXPECTED_GECKO_ID = "{EXPECTED_GECKO_ID}"',
            '"host_permissions"',
            '"optional_host_permissions"',
            'collection != {"required": ["none"]}',
            '"strict_min_version" in gecko',
            '"package_only_not_live_runtime"',
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_completeness_review_ui_is_explicitly_non_authoritative(self):
        html = (EXTENSION / "popup.html").read_text(encoding="utf-8")
        source = (EXTENSION / "popup.js").read_text(encoding="utf-8")

        for element_id in [
            "first-role",
            "last-role",
            "same-role-transitions",
            "ignored-role-nodes",
            "empty-role-nodes",
            "completeness-status",
            "first-user",
            "first-assistant",
            "last-user",
            "last-assistant",
        ]:
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', html)

        self.assertIn("DOM completeness: not proven.", html)
        self.assertIn("virtualize or unload earlier messages", html)
        self.assertIn("run <strong>Inspect conversation</strong> again", html)
        self.assertIn("function firstMessage(role)", source)
        self.assertIn("function lastMessage(role)", source)
        self.assertIn("function sequenceReview(messages)", source)
        self.assertIn("messages[index].role === messages[index - 1].role", source)
        self.assertIn('completenessStatusNode.textContent = "Not proven"', source)
        self.assertIn("firstUserNode.textContent = previewText", source)
        self.assertIn("lastAssistantNode.textContent = previewText", source)
        self.assertIn("DOM completeness is not proven", source)

        combined = (html + "\n" + source).lower().replace(" ", "")
        self.assertNotIn("complete=true", combined)
        self.assertNotIn("completeness=true", combined)

    def test_intermediate_schema_is_allowlisted_and_unchanged_by_ui_review_metrics(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema_version"]["const"], "paic-browser-capture-1")
        self.assertEqual(schema["properties"]["messages"]["items"]["properties"]["role"]["enum"], ["user", "assistant"])
        for forbidden_field in [
            "url",
            "title",
            "cookies",
            "headers",
            "session",
            "account",
            "complete",
            "completeness",
        ]:
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
