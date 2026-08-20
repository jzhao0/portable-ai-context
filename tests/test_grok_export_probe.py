import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from tools.grok_export_probe import (
    ASSISTANT_MARKER_DEFAULT,
    ProbeError,
    USER_MARKER_DEFAULT,
    main,
    run_probe,
)


USER = USER_MARKER_DEFAULT
ASSISTANT = ASSISTANT_MARKER_DEFAULT


def _kwargs(source: Path, output: Path, **overrides):
    values = {
        "source": source,
        "output": output,
        "user_marker": USER,
        "assistant_marker": ASSISTANT,
        "max_json_mb": 4,
        "max_total_json_mb": 8,
        "max_documents": 100,
        "max_zip_members": 100,
        "max_nodes": 10000,
        "max_depth": 32,
        "max_specimen_kb": 128,
    }
    values.update(overrides)
    return values


class GrokUnknownSchemaProbeTests(unittest.TestCase):
    def test_unknown_field_names_find_minimal_context_and_redact_values(self):
        private_url_key = "https://grok.example/private/conversation/opaque-id"
        export = {
            "account": {
                "email": "PRIVATE_ACCOUNT@example.invalid",
                "token": "PRIVATE_SESSION_TOKEN",
            },
            "totally_unknown_collection": [
                {
                    "opaque": "OTHER_PRIVATE_RECORD",
                    "nested": [{"speakerish": "user", "bodyish": "OTHER_PRIVATE_TEXT"}],
                },
                {
                    "conversationish": {
                        "private_uuid": "123e4567-e89b-12d3-a456-426614174000",
                        private_url_key: "PRIVATE_MAP_VALUE",
                        "entries": [
                            {
                                "speakerish": "user",
                                "bodyish": f"prefix PRIVATE_NEIGHBOR {USER} suffix",
                                "timestampish": "2026-08-20T10:00:00+08:00",
                            },
                            {
                                "speakerish": "assistant",
                                "bodyish": f"{ASSISTANT} PRIVATE_ASSISTANT_NEIGHBOR",
                                "opaque_id": "A" * 64,
                            },
                        ],
                    },
                    "outside_private": "SHOULD_NOT_BE_IN_MINIMAL_CONTEXT",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "download.json"
            output = root / "safe.json"
            source.write_text(json.dumps(export), encoding="utf-8")

            report = run_probe(**_kwargs(source, output))
            safe = output.read_text(encoding="utf-8")

        self.assertTrue(report["ok"])
        self.assertEqual(report["provider"], "grok")
        self.assertEqual(report["matched_minimal_contexts"], 1)
        self.assertFalse(report["schema_fields_assumed"])
        self.assertTrue(report["raw_export_not_copied"])
        self.assertGreaterEqual(report["user_marker_occurrences_in_context"], 1)
        self.assertGreaterEqual(report["assistant_marker_occurrences_in_context"], 1)

        self.assertIn(USER, safe)
        self.assertIn(ASSISTANT, safe)
        self.assertIn('"speakerish": "user"', safe)
        self.assertIn('"speakerish": "assistant"', safe)
        self.assertIn('"bodyish"', safe)
        self.assertIn("<redacted-key-", safe)

        for forbidden in [
            "PRIVATE_ACCOUNT@example.invalid",
            "PRIVATE_SESSION_TOKEN",
            "OTHER_PRIVATE_RECORD",
            "OTHER_PRIVATE_TEXT",
            "123e4567-e89b-12d3-a456-426614174000",
            private_url_key,
            "PRIVATE_MAP_VALUE",
            "PRIVATE_NEIGHBOR",
            "PRIVATE_ASSISTANT_NEIGHBOR",
            "2026-08-20T10:00:00+08:00",
            "A" * 64,
            "SHOULD_NOT_BE_IN_MINIMAL_CONTEXT",
        ]:
            self.assertNotIn(forbidden, safe)

    def test_jsonl_and_ndjson_are_scanned_without_field_assumptions(self):
        records = [
            {"x": "PRIVATE_OTHER"},
            {
                "mystery": [
                    {"kind": "human", "payload": USER},
                    {"kind": "model", "payload": ASSISTANT},
                ]
            },
        ]
        for suffix in [".jsonl", ".ndjson"]:
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                source = root / f"download{suffix}"
                output = root / "safe.json"
                source.write_text(
                    "\n".join(json.dumps(record) for record in records) + "\n",
                    encoding="utf-8",
                )
                report = run_probe(**_kwargs(source, output))
                safe = output.read_text(encoding="utf-8")

            self.assertEqual(report["jsonl_ndjson_files_seen"], 1)
            self.assertEqual(report["parsed_documents_scanned"], 2)
            self.assertIn(USER, safe)
            self.assertIn(ASSISTANT, safe)
            self.assertNotIn("PRIVATE_OTHER", safe)

    def test_zip_counts_html_but_never_reads_it_as_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "xai-download.zip"
            output = root / "safe.json"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("private.html", f"PRIVATE_HTML {USER} {ASSISTANT}")
                handle.writestr(
                    "nested/data.json",
                    json.dumps(
                        {
                            "wrapper": {
                                "events": [
                                    {"roleish": "user", "value": USER},
                                    {"roleish": "assistant", "value": ASSISTANT},
                                ]
                            }
                        }
                    ),
                )

            report = run_probe(**_kwargs(archive, output))
            safe = output.read_text(encoding="utf-8")

        self.assertEqual(report["html_documents_seen"], 1)
        self.assertIn(USER, safe)
        self.assertIn(ASSISTANT, safe)
        self.assertNotIn("PRIVATE_HTML", safe)

    def test_html_only_source_fails_content_free(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "export"
            source.mkdir()
            (source / "private.html").write_text(
                f"PRIVATE_HTML_BODY {USER} {ASSISTANT}", encoding="utf-8"
            )
            with self.assertRaisesRegex(ProbeError, "no readable JSON/JSONL/NDJSON") as caught:
                run_probe(**_kwargs(source, root / "safe.json"))

        self.assertIn("HTML documents seen: 1", str(caught.exception))
        self.assertNotIn("PRIVATE_HTML_BODY", str(caught.exception))

    def test_multiple_minimal_contexts_fail_closed(self):
        export = {
            "records": [
                {"parts": [{"x": USER}, {"x": ASSISTANT}]},
                {"parts": [{"y": USER}, {"y": ASSISTANT}]},
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "download.json"
            source.write_text(json.dumps(export), encoding="utf-8")
            with self.assertRaisesRegex(ProbeError, "found multiple"):
                run_probe(**_kwargs(source, root / "safe.json"))

    def test_root_list_without_dictionary_context_fails_closed(self):
        export = [{"x": USER}, {"x": ASSISTANT}]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "download.json"
            source.write_text(json.dumps(export), encoding="utf-8")
            with self.assertRaisesRegex(ProbeError, "found none"):
                run_probe(**_kwargs(source, root / "safe.json"))

    def test_per_document_size_limit_fails_without_content_echo(self):
        private = "PRIVATE_LARGE_CONTENT_" * 100
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "large.json"
            source.write_text(json.dumps({"private": private}), encoding="utf-8")
            with self.assertRaisesRegex(ProbeError, "per-document limit") as caught:
                run_probe(**_kwargs(source, root / "safe.json", max_json_mb=1))
        self.assertNotIn(private, str(caught.exception))

    def test_total_document_limit_fails_closed_for_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "records.jsonl"
            source.write_text(
                "\n".join(json.dumps({"x": index}) for index in range(4)) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProbeError, "document limit"):
                run_probe(**_kwargs(source, root / "safe.json", max_documents=2))

    def test_node_limit_and_depth_limit_fail_closed(self):
        node_heavy = {"items": [{"x": index} for index in range(50)], "u": USER, "a": ASSISTANT}
        deep = {"leaf": [USER, ASSISTANT]}
        for index in range(10):
            deep = {f"level{index}": deep}

        cases = [
            (node_heavy, {"max_nodes": 20}, "node limit"),
            (deep, {"max_depth": 4}, "depth limit"),
        ]
        for payload, overrides, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                source = root / "download.json"
                source.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ProbeError, expected):
                    run_probe(**_kwargs(source, root / "safe.json", **overrides))

    def test_specimen_limit_fails_instead_of_truncating(self):
        export = {
            "conversation": {
                "large_structure": [{f"field_{i}": "PRIVATE"} for i in range(200)],
                "messages": [{"x": USER}, {"x": ASSISTANT}],
            }
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "download.json"
            output = root / "safe.json"
            source.write_text(json.dumps(export), encoding="utf-8")
            with self.assertRaisesRegex(ProbeError, "specimen exceeded"):
                run_probe(**_kwargs(source, output, max_specimen_kb=1))
            self.assertFalse(output.exists())

    def test_cli_read_error_does_not_echo_private_local_path(self):
        private_path = r"C:\Users\PRIVATE_USER\Secret xAI Export\download.zip"
        stderr = io.StringIO()
        with mock.patch(
            "tools.grok_export_probe.run_probe",
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

    def test_report_contains_basename_not_private_output_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "PRIVATE_USER" / "Secret"
            root.mkdir(parents=True)
            source = root / "download.json"
            output = root / "safe-result.json"
            source.write_text(
                json.dumps({"unknown": [{"x": USER}, {"y": ASSISTANT}]}),
                encoding="utf-8",
            )
            report = run_probe(**_kwargs(source, output))

        encoded = json.dumps(report)
        self.assertEqual(report["output_file"], "safe-result.json")
        self.assertNotIn("PRIVATE_USER", encoded)
        self.assertNotIn("Secret", encoded)


if __name__ == "__main__":
    unittest.main()
