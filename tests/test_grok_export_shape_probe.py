import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from tools.grok_export_shape_probe import (
    DEFAULT_ASSISTANT_SENTINEL,
    DEFAULT_USER_SENTINEL,
    ProbeError,
    main,
    run_probe,
)


class GrokExportShapeProbeTests(unittest.TestCase):
    def test_unknown_object_shape_selects_minimal_common_context_and_redacts_values(self):
        export = {
            "account": {
                "email": "PRIVATE_ACCOUNT@example.invalid",
                "numeric": 123456789,
            },
            "totally_unknown_provider_container": [
                {
                    "opaque": "OTHER_PRIVATE_ITEM",
                    "nested": {"body": "OTHER_PRIVATE_TEXT"},
                },
                {
                    "private-conversation-id": "PRIVATE_CONVERSATION_ID",
                    "unknown_turns": [
                        {
                            "speaker": "user",
                            "payload": DEFAULT_USER_SENTINEL,
                            "created": "2026-08-19T15:00:00Z",
                            "opaque-id": "0123456789abcdef0123456789abcdef",
                        },
                        {
                            "speaker": "assistant",
                            "payload": DEFAULT_ASSISTANT_SENTINEL,
                            "metadata": {
                                "normal_private_value": "DO_NOT_SHARE_ME",
                                "https://private.example/account/secret": "PRIVATE_URL_KEY_VALUE",
                            },
                        },
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "xai-account-download.zip"
            output = root / "safe.json"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("unknown-provider-data.json", json.dumps(export))
                handle.writestr("account.html", "PRIVATE_HTML_ACCOUNT_CONTENT")
                handle.writestr("avatar.bin", b"PRIVATE_BINARY")

            report = run_probe(
                source=archive,
                user_sentinel=DEFAULT_USER_SENTINEL,
                assistant_sentinel=DEFAULT_ASSISTANT_SENTINEL,
                output=output,
                max_document_mb=10,
                max_specimen_nodes=500,
            )
            safe = output.read_text(encoding="utf-8")

        self.assertTrue(report["ok"])
        self.assertEqual(report["provider"], "grok")
        self.assertEqual(
            report["probe_mode"],
            "unknown_schema_minimal_common_container_v1",
        )
        self.assertEqual(report["user_sentinel_occurrences"], 1)
        self.assertEqual(report["assistant_sentinel_occurrences"], 1)
        self.assertEqual(report["minimal_context_type"], "object")
        self.assertFalse(report["schema_claimed"])
        self.assertTrue(report["raw_export_not_copied"])
        self.assertEqual(report["html_documents_seen"], 1)
        self.assertEqual(report["other_files_seen"], 1)

        self.assertIn(DEFAULT_USER_SENTINEL, safe)
        self.assertIn(DEFAULT_ASSISTANT_SENTINEL, safe)
        self.assertIn('"unknown_turns"', safe)
        self.assertIn('"speaker": "user"', safe)
        self.assertIn('"speaker": "assistant"', safe)
        self.assertIn('"<redacted-key>"', safe)
        for forbidden in [
            "PRIVATE_ACCOUNT@example.invalid",
            "OTHER_PRIVATE_ITEM",
            "OTHER_PRIVATE_TEXT",
            "PRIVATE_CONVERSATION_ID",
            "2026-08-19T15:00:00Z",
            "0123456789abcdef0123456789abcdef",
            "DO_NOT_SHARE_ME",
            "https://private.example/account/secret",
            "PRIVATE_URL_KEY_VALUE",
            "PRIVATE_HTML_ACCOUNT_CONTENT",
            "PRIVATE_BINARY",
        ]:
            self.assertNotIn(forbidden, safe)

    def test_root_array_is_supported_without_schema_guess(self):
        export = [
            {"kind": "user", "value": DEFAULT_USER_SENTINEL},
            {"kind": "assistant", "value": DEFAULT_ASSISTANT_SENTINEL},
        ]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "unknown.json"
            output = root / "safe.json"
            source.write_text(json.dumps(export), encoding="utf-8")
            report = run_probe(
                source=source,
                user_sentinel=DEFAULT_USER_SENTINEL,
                assistant_sentinel=DEFAULT_ASSISTANT_SENTINEL,
                output=output,
                max_document_mb=10,
                max_specimen_nodes=100,
            )
        self.assertEqual(report["minimal_context_type"], "array")
        self.assertFalse(report["schema_claimed"])

    def test_jsonl_is_scanned_without_assuming_record_keys(self):
        records = [
            {"first": DEFAULT_USER_SENTINEL, "private": "SECRET_ONE"},
            {"second": DEFAULT_ASSISTANT_SENTINEL, "private": "SECRET_TWO"},
        ]
        # Two independent JSONL records do not have one shared JSON container, so
        # discovery must fail rather than invent a conversation boundary.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "unknown.jsonl"
            source.write_text(
                "\n".join(json.dumps(item) for item in records) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProbeError, "minimal JSON container"):
                run_probe(
                    source=source,
                    user_sentinel=DEFAULT_USER_SENTINEL,
                    assistant_sentinel=DEFAULT_ASSISTANT_SENTINEL,
                    output=root / "safe.json",
                    max_document_mb=10,
                    max_specimen_nodes=100,
                )

    def test_duplicate_sentinel_occurrences_fail_closed_without_private_content(self):
        export = {
            "container": [
                {"x": DEFAULT_USER_SENTINEL},
                {"x": DEFAULT_USER_SENTINEL},
                {"x": DEFAULT_ASSISTANT_SENTINEL},
            ],
            "private": "PRIVATE_UNRELATED_TEXT",
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "unknown.json"
            source.write_text(json.dumps(export), encoding="utf-8")
            with self.assertRaisesRegex(ProbeError, "user occurrences: 2") as raised:
                run_probe(
                    source=source,
                    user_sentinel=DEFAULT_USER_SENTINEL,
                    assistant_sentinel=DEFAULT_ASSISTANT_SENTINEL,
                    output=root / "safe.json",
                    max_document_mb=10,
                    max_specimen_nodes=100,
                )
        self.assertNotIn("PRIVATE_UNRELATED_TEXT", str(raised.exception))

    def test_oversized_context_refuses_instead_of_truncating(self):
        export = {
            "turns": [
                {"role": "user", "text": DEFAULT_USER_SENTINEL},
                *({"role": "system", "text": f"PRIVATE_{index}"} for index in range(40)),
                {"role": "assistant", "text": DEFAULT_ASSISTANT_SENTINEL},
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "unknown.json"
            source.write_text(json.dumps(export), encoding="utf-8")
            with self.assertRaisesRegex(ProbeError, "structural node limit") as raised:
                run_probe(
                    source=source,
                    user_sentinel=DEFAULT_USER_SENTINEL,
                    assistant_sentinel=DEFAULT_ASSISTANT_SENTINEL,
                    output=root / "safe.json",
                    max_document_mb=10,
                    max_specimen_nodes=10,
                )
        self.assertNotIn("PRIVATE_", str(raised.exception))

    def test_html_only_failure_is_content_free(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "history.html").write_text(
                "PRIVATE_HTML " + DEFAULT_USER_SENTINEL,
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProbeError, "HTML documents seen: 1") as raised:
                run_probe(
                    source=root,
                    user_sentinel=DEFAULT_USER_SENTINEL,
                    assistant_sentinel=DEFAULT_ASSISTANT_SENTINEL,
                    output=root / "safe.json",
                    max_document_mb=10,
                    max_specimen_nodes=100,
                )
        self.assertNotIn("PRIVATE_HTML", str(raised.exception))

    def test_local_read_error_does_not_print_private_path(self):
        private_path = r"C:\Users\PRIVATE_USER\Secret xAI Export\download.zip"
        stderr = io.StringIO()
        with mock.patch(
            "tools.grok_export_shape_probe.run_probe",
            side_effect=PermissionError(13, "permission denied", private_path),
        ):
            with contextlib.redirect_stderr(stderr):
                code = main([private_path])
        error = stderr.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("PermissionError", error)
        self.assertNotIn("PRIVATE_USER", error)
        self.assertNotIn("Secret xAI Export", error)
        self.assertNotIn(private_path, error)


if __name__ == "__main__":
    unittest.main()
