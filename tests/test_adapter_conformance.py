import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from _helpers import sample_conversation, synthetic_chatgpt_html
from portable_ai_context.adapters.registry import load_conversation
from portable_ai_context.cli import main as cli_main
from portable_ai_context.conformance import inspect_conformance
from portable_ai_context.exporters import clean_html, compact_txt, jsonl
from portable_ai_context.models import Conversation, Message, SourceInfo


FIXTURES = Path(__file__).parent / "fixtures"


class AdapterConformanceTests(unittest.TestCase):
    def test_shared_contract_passes_representative_current_adapters(self):
        sample = sample_conversation()
        cases = []

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            jsonl_path = root / "conversation.jsonl"
            jsonl_path.write_text(jsonl(sample), encoding="utf-8")
            cases.append(
                (
                    "jsonl",
                    jsonl_path,
                    "jsonl",
                    [(m.role, m.text) for m in sample.messages],
                    (),
                )
            )

            txt_path = root / "conversation.txt"
            txt_path.write_text(compact_txt(sample), encoding="utf-8")
            cases.append(
                (
                    "compact_txt",
                    txt_path,
                    "compact_txt",
                    [(m.role, m.text) for m in sample.messages],
                    (),
                )
            )

            clean_path = root / "conversation.clean.html"
            clean_path.write_text(clean_html(sample), encoding="utf-8")
            cases.append(
                (
                    "clean_html",
                    clean_path,
                    "clean_html",
                    [(m.role, m.text) for m in sample.messages],
                    (),
                )
            )

            chatgpt_path = root / "chatgpt-share.html"
            chatgpt_path.write_text(synthetic_chatgpt_html(), encoding="utf-8")
            cases.append(
                (
                    "chatgpt_html",
                    chatgpt_path,
                    "chatgpt_html",
                    [
                        ("user", "Hello from user"),
                        ("assistant", "Hello from assistant"),
                    ],
                    (),
                )
            )

            claude_path = root / "claude.json"
            claude_path.write_text(
                (FIXTURES / "claude_conversation.synthetic.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            cases.append(
                (
                    "claude_json",
                    claude_path,
                    "claude_json",
                    [
                        ("user", "Build the portable context adapter."),
                        ("assistant", "The adapter is implemented."),
                        ("user", "Verify the privacy boundary."),
                        ("assistant", "Privacy boundary verified."),
                    ],
                    (
                        "PRIVATE_ACCOUNT@example.invalid",
                        "PRIVATE_USER_ID",
                        "PRIVATE_ORG_ID",
                        "PRIVATE_SESSION_TOKEN",
                        "PRIVATE_REASONING_BLOCK",
                        "PRIVATE_TOOL_TOKEN",
                        "PRIVATE_SYSTEM_RUNTIME_MESSAGE",
                        "private-runtime-model",
                    ),
                )
            )

            gemini_path = root / "gemini.json"
            gemini_path.write_text(
                (FIXTURES / "gemini_my_activity.synthetic.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            cases.append(
                (
                    "gemini_my_activity_json",
                    gemini_path,
                    "gemini_my_activity_json",
                    [
                        ("user", "Build a privacy-safe Gemini activity adapter."),
                        (
                            "assistant",
                            "The Gemini activity adapter is implemented.\nOnly supported text crosses the boundary.",
                        ),
                        ("user", "Verify the Gemini adapter tail."),
                        ("assistant", "Tail verification passed.\n2/2 messages preserved"),
                    ],
                    (
                        "PRIVATE_EMBEDDED_SCRIPT",
                        "PRIVATE_EMBEDDED_STYLE",
                        "PRIVATE_LOCATION",
                        "PRIVATE_GEMINI_ACCOUNT@example.invalid",
                        "PRIVATE_GEMINI_USER_ID",
                        "PRIVATE_GEMINI_SESSION_TOKEN",
                        "PRIVATE_NON_GEMINI_PROMPT",
                        "PRIVATE_NON_GEMINI_RESPONSE",
                        "PRIVATE_RUNTIME_DETAIL",
                        "PRIVATE_AUTHORIZATION_VALUE",
                    ),
                )
            )

            for name, path, expected_source, expected_messages, forbidden in cases:
                with self.subTest(adapter=name):
                    conversation = load_conversation(str(path))
                    self.assertEqual(conversation.source.kind, expected_source)
                    report = inspect_conformance(
                        conversation,
                        expected_messages=expected_messages,
                        forbidden_values=forbidden,
                    )
                    self.assertTrue(report.ok, report.to_dict())
                    self.assertTrue(all(report.checks.values()), report.to_dict())

    def test_negative_contract_reports_codes_without_echoing_private_values(self):
        private_value = "PRIVATE_RUNTIME_SECRET_DO_NOT_ECHO"
        conversation = Conversation(
            title="synthetic",
            source=SourceInfo(
                kind="synthetic",
                metadata={"unsafe_runtime_value": private_value},
            ),
            messages=[
                Message(role="system", text="not canonical", index=4),
                Message(role="assistant", text="", index=8),
            ],
        )

        report = inspect_conformance(
            conversation,
            expected_messages=[("user", "expected")],
            forbidden_values=[private_value],
        )
        payload = json.dumps(report.to_dict())

        self.assertFalse(report.ok)
        codes = {item.code for item in report.violations}
        self.assertIn("noncanonical_role", codes)
        self.assertIn("noncontiguous_indices", codes)
        self.assertIn("empty_message_text", codes)
        self.assertIn("expected_messages_mismatch", codes)
        self.assertIn("forbidden_value_present", codes)
        self.assertNotIn(private_value, payload)

    def test_cli_conform_output_is_content_free(self):
        fixture = FIXTURES / "claude_conversation.synthetic.json"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_main(["conform", str(fixture)])
        output = stdout.getvalue()
        report = json.loads(output)

        self.assertEqual(code, 0)
        self.assertTrue(report["ok"])
        self.assertEqual(report["source_kind"], "claude_json")
        self.assertEqual(report["message_count"], 4)
        self.assertNotIn("Synthetic Claude Project", output)
        self.assertNotIn("Build the portable context adapter.", output)
        self.assertNotIn("Privacy boundary verified.", output)
        self.assertNotIn("PRIVATE_ACCOUNT@example.invalid", output)
        self.assertNotIn(str(fixture), output)


if __name__ == "__main__":
    unittest.main()
