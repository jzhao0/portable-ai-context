import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.real_export_probe import ProbeError, run_probe


CLAUDE_SENTINEL = "PAIC_CLAUDE_REAL_EXPORT_SENTINEL_20260819"
GEMINI_SENTINEL = "PAIC_GEMINI_REAL_EXPORT_SENTINEL_20260819"


class RealExportProbeTests(unittest.TestCase):
    def test_claude_zip_selects_one_record_and_redacts_private_values(self):
        export = [
            {
                "uuid": "PRIVATE_CLAUDE_CONVERSATION_UUID",
                "name": CLAUDE_SENTINEL,
                "created_at": "2026-08-19T01:00:00Z",
                "account": {
                    "email": "PRIVATE_CLAUDE_ACCOUNT@example.invalid",
                    "user_id": "PRIVATE_CLAUDE_USER_ID",
                },
                "chat_messages": [
                    {
                        "sender": "human",
                        "text": CLAUDE_SENTINEL,
                        "uuid": "PRIVATE_USER_MESSAGE_UUID",
                    },
                    {
                        "sender": "assistant",
                        "text": CLAUDE_SENTINEL + "_OK",
                        "content": [{"type": "text", "text": CLAUDE_SENTINEL + "_OK"}],
                        "uuid": "PRIVATE_ASSISTANT_MESSAGE_UUID",
                    },
                ],
            },
            {
                "uuid": "OTHER_PRIVATE_UUID",
                "name": "PRIVATE_OTHER_CONVERSATION",
                "chat_messages": [{"sender": "human", "text": "PRIVATE_OTHER_TEXT"}],
            },
        ]

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "claude-export.zip"
            output = root / "safe.json"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("conversations.json", json.dumps(export))
                handle.writestr("account.json", json.dumps({"email": "PRIVATE_TOP_LEVEL@example.invalid"}))

            report = run_probe(
                provider="claude",
                source=archive,
                sentinel=CLAUDE_SENTINEL,
                output=output,
                max_json_mb=10,
            )
            safe = output.read_text(encoding="utf-8")

        self.assertTrue(report["ok"])
        self.assertEqual(report["provider"], "claude")
        self.assertEqual(report["matched_records"], 1)
        self.assertTrue(report["raw_export_not_copied"])
        self.assertIn(CLAUDE_SENTINEL, safe)
        self.assertIn('"chat_messages"', safe)
        self.assertIn('"sender": "human"', safe)
        self.assertIn('"sender": "assistant"', safe)
        for forbidden in [
            "PRIVATE_CLAUDE_CONVERSATION_UUID",
            "PRIVATE_CLAUDE_ACCOUNT@example.invalid",
            "PRIVATE_CLAUDE_USER_ID",
            "PRIVATE_USER_MESSAGE_UUID",
            "PRIVATE_ASSISTANT_MESSAGE_UUID",
            "PRIVATE_OTHER_CONVERSATION",
            "PRIVATE_OTHER_TEXT",
            "PRIVATE_TOP_LEVEL@example.invalid",
        ]:
            self.assertNotIn(forbidden, safe)

    def test_gemini_json_preserves_parser_literals_but_redacts_runtime_values(self):
        export = [
            {
                "header": "Gemini Apps",
                "title": f"Prompted {GEMINI_SENTINEL}",
                "time": "2026-08-19T02:00:00Z",
                "products": ["Gemini Apps"],
                "safeHtmlItem": [{"html": f"<p>{GEMINI_SENTINEL}_OK</p>"}],
                "details": f"PRIVATE_NEIGHBOR_BEFORE {GEMINI_SENTINEL} PRIVATE_NEIGHBOR_AFTER",
                "locationInfos": "PRIVATE_LOCATION",
                "account": {"email": "PRIVATE_GEMINI_ACCOUNT@example.invalid"},
                "sessionToken": "PRIVATE_GEMINI_SESSION_TOKEN",
            },
            {
                "header": "Gemini Apps",
                "title": "Prompted PRIVATE_OTHER_PROMPT",
                "products": ["Gemini Apps"],
                "safeHtmlItem": [{"html": "PRIVATE_OTHER_RESPONSE"}],
            },
        ]

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "MyActivity.json"
            output = root / "safe.json"
            source.write_text(json.dumps(export), encoding="utf-8")

            report = run_probe(
                provider="gemini",
                source=source,
                sentinel=GEMINI_SENTINEL,
                output=output,
                max_json_mb=10,
            )
            safe = output.read_text(encoding="utf-8")

        self.assertEqual(report["matched_records"], 1)
        self.assertIn('"header": "Gemini Apps"', safe)
        self.assertIn(f"Prompted {GEMINI_SENTINEL}", safe)
        self.assertIn(GEMINI_SENTINEL + "_OK", safe)
        for forbidden in [
            "2026-08-19T02:00:00Z",
            "PRIVATE_NEIGHBOR_BEFORE",
            "PRIVATE_NEIGHBOR_AFTER",
            "PRIVATE_LOCATION",
            "PRIVATE_GEMINI_ACCOUNT@example.invalid",
            "PRIVATE_GEMINI_SESSION_TOKEN",
            "PRIVATE_OTHER_PROMPT",
            "PRIVATE_OTHER_RESPONSE",
        ]:
            self.assertNotIn(forbidden, safe)

    def test_multiple_matching_provider_records_fail_closed(self):
        export = [
            {"chat_messages": [{"sender": "human", "text": CLAUDE_SENTINEL}]},
            {"chat_messages": [{"sender": "human", "text": CLAUDE_SENTINEL}]},
        ]
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "conversations.json"
            source.write_text(json.dumps(export), encoding="utf-8")
            with self.assertRaisesRegex(ProbeError, "expected exactly one"):
                run_probe(
                    provider="claude",
                    source=source,
                    sentinel=CLAUDE_SENTINEL,
                    output=Path(td) / "safe.json",
                    max_json_mb=10,
                )

    def test_html_only_export_does_not_dump_content(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "export"
            source.mkdir()
            (source / "MyActivity.html").write_text(
                "PRIVATE_HTML_CONTENT " + GEMINI_SENTINEL,
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProbeError, "no readable JSON documents") as raised:
                run_probe(
                    provider="gemini",
                    source=source,
                    sentinel=GEMINI_SENTINEL,
                    output=Path(td) / "safe.json",
                    max_json_mb=10,
                )
        self.assertNotIn("PRIVATE_HTML_CONTENT", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
