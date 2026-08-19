import contextlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from _helpers import sample_conversation
from portable_ai_context.checkpoint import (
    MIN_BUDGET_TOKENS,
    OMISSION_LABEL,
    POLICY_VERSION,
    build_extractive_checkpoint,
)
from portable_ai_context.cli import main as cli_main
from portable_ai_context.compiler import CallableTokenCounter
from portable_ai_context.errors import PortableAIContextError
from portable_ai_context.models import Conversation, Message, SourceInfo


def exact_words():
    return CallableTokenCounter(
        fn=lambda text: len(text.split()),
        name="fake_exact_words",
        exact=True,
    )


def exact_characters():
    return CallableTokenCounter(
        fn=len,
        name="fake_exact_characters",
        exact=True,
    )


def long_state_conversation(message_count: int = 80) -> Conversation:
    messages = []
    for index in range(message_count):
        role = "user" if index % 2 == 0 else "assistant"
        text = f"neutral historical message {index} " + "context " * 18
        if index == 0:
            text = "Original goal: build a deterministic portable handoff without network calls. " + "goal " * 12
        if index == 2:
            text = (
                "下一步必须继续处理这个未完成问题，当前阻塞等待验证，版本提交确认后再继续。 "
                + "state " * 12
            )
        if index == message_count - 2:
            text = "Latest user request: continue the current checkpoint implementation. " + "recent " * 15
        if index == message_count - 1:
            text = "Latest assistant status: implementation is pending final tests. " + "recent " * 15
        messages.append(Message(role=role, text=text, index=index))
    return Conversation(
        title="Long synthetic state",
        source=SourceInfo(kind="synthetic"),
        messages=messages,
    )


class DeterministicCheckpointTests(unittest.TestCase):
    def test_short_conversation_default_standard_preserves_all_messages(self):
        conversation = sample_conversation()
        result = build_extractive_checkpoint(conversation)

        self.assertEqual(result.report.policy, POLICY_VERSION)
        self.assertEqual(result.report.profile, "standard")
        self.assertEqual(result.report.budget_tokens, 16_000)
        self.assertEqual(result.report.selected_indices, [0, 1, 2, 3])
        self.assertEqual(result.report.selected_message_count, 4)
        self.assertTrue(result.report.first_user_included)
        self.assertTrue(result.report.latest_user_included)
        self.assertTrue(result.report.latest_assistant_included)
        self.assertEqual(result.report.truncated_message_count, 0)
        self.assertTrue(result.report.budget_met)
        self.assertIn("deterministic extractive evidence, not an AI summary", result.markdown)
        for message in conversation.messages:
            self.assertIn(message.text, result.markdown)

    def test_budgeted_long_conversation_preserves_anchors_and_older_state_marker(self):
        conversation = long_state_conversation()
        result = build_extractive_checkpoint(
            conversation,
            budget_tokens=512,
            token_counter=exact_words(),
        )

        self.assertTrue(result.report.budget_met)
        self.assertLessEqual(result.report.output_token_estimate, 512)
        self.assertTrue(result.report.first_user_included)
        self.assertTrue(result.report.latest_user_included)
        self.assertTrue(result.report.latest_assistant_included)
        self.assertIn(2, result.report.selected_indices)
        self.assertEqual(result.report.selected_indices, sorted(result.report.selected_indices))
        self.assertIn("下一步", result.markdown)
        self.assertRegex(
            result.markdown,
            r"(?s)### SOURCE MESSAGE 3 \[USER\].*?- state_marker_hits: [1-9][0-9]*",
        )
        self.assertIn("selection_reason: latest_user", result.markdown)
        self.assertIn("selection_reason: latest_assistant", result.markdown)

    def test_long_selected_message_uses_explicit_omission_marker_with_real_evidence(self):
        long_text = "HEAD_EVIDENCE_" + ("x" * 8_000) + "_TAIL_EVIDENCE"
        conversation = Conversation(
            title="Truncation synthetic",
            source=SourceInfo(kind="synthetic"),
            messages=[
                Message(role="user", text=long_text, index=0),
                Message(role="assistant", text="Latest assistant evidence remains visible.", index=1),
            ],
        )
        result = build_extractive_checkpoint(
            conversation,
            budget_tokens=3_000,
            token_counter=exact_characters(),
        )

        self.assertTrue(result.report.budget_met)
        self.assertGreaterEqual(result.report.truncated_message_count, 1)
        self.assertIn(OMISSION_LABEL, result.markdown)
        self.assertIn("HEAD_EVIDENCE_", result.markdown)
        self.assertIn("_TAIL_EVIDENCE", result.markdown)
        self.assertRegex(result.markdown, r"PAIC DETERMINISTIC OMISSION: [1-9][0-9]* CHARACTERS OMITTED")
        self.assertLessEqual(result.report.output_token_estimate, 3_000)

    def test_supported_secret_patterns_are_redacted_only_in_derived_artifact(self):
        openai_key = "sk-ABCDEFGHIJKLMNOPQRSTUVWX"
        github_token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        aws_key = "AKIAABCDEFGHIJKLMNOP"
        bearer = "Bearer abcdefghijklmnopqrstuvwxyz1234567890"
        private_key = (
            "-----BEGIN PRIVATE KEY-----\n"
            "ABCDEF0123456789ABCDEF0123456789\n"
            "-----END PRIVATE KEY-----"
        )
        original_text = (
            f"Secrets typed as content: {openai_key} {github_token} {aws_key} {bearer}\n{private_key}"
        )
        conversation = Conversation(
            title="Secret redaction synthetic",
            source=SourceInfo(
                kind="synthetic",
                locator=r"C:\Users\PRIVATE_USER\Secret Project\raw-export.json",
            ),
            messages=[
                Message(role="user", text=original_text, index=0),
                Message(role="assistant", text="Acknowledged without repeating credentials.", index=1),
            ],
        )

        result = build_extractive_checkpoint(conversation, profile="full")
        report_json = json.dumps(result.report.to_dict(), sort_keys=True)

        for secret in [openai_key, github_token, aws_key, bearer, private_key]:
            self.assertNotIn(secret, result.markdown)
            self.assertNotIn(secret, report_json)
        self.assertIn("[REDACTED:openai_style_key]", result.markdown)
        self.assertIn("[REDACTED:github_token]", result.markdown)
        self.assertIn("[REDACTED:aws_access_key]", result.markdown)
        self.assertIn("[REDACTED:bearer_token]", result.markdown)
        self.assertIn("[REDACTED:private_key_material]", result.markdown)
        self.assertGreater(result.report.redaction_counts["openai_style_key"], 0)
        self.assertGreater(result.report.redaction_counts["github_token"], 0)
        self.assertGreater(result.report.redaction_counts["aws_access_key"], 0)
        self.assertGreater(result.report.redaction_counts["bearer_token"], 0)
        self.assertGreater(result.report.redaction_counts["private_key_material"], 0)
        self.assertNotIn("PRIVATE_USER", result.markdown)
        self.assertNotIn("Secret Project", result.markdown)
        self.assertNotIn("PRIVATE_USER", report_json)
        self.assertEqual(conversation.messages[0].text, original_text)

    def test_same_input_and_options_are_byte_deterministic(self):
        conversation = long_state_conversation()
        first = build_extractive_checkpoint(
            conversation,
            budget_tokens=700,
            token_counter=exact_words(),
        )
        second = build_extractive_checkpoint(
            conversation,
            budget_tokens=700,
            token_counter=exact_words(),
        )

        first_report = json.dumps(first.report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        second_report = json.dumps(second.report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self.assertEqual(first.markdown.encode("utf-8"), second.markdown.encode("utf-8"))
        self.assertEqual(first_report.encode("utf-8"), second_report.encode("utf-8"))

    def test_python_api_rejects_too_small_budget_and_nonconforming_input(self):
        with self.assertRaisesRegex(ValueError, str(MIN_BUDGET_TOKENS)):
            build_extractive_checkpoint(sample_conversation(), budget_tokens=MIN_BUDGET_TOKENS - 1)

        invalid = Conversation(
            title="invalid",
            source=SourceInfo(kind="synthetic"),
            messages=[Message(role="system", text="not canonical", index=0)],
        )
        with self.assertRaisesRegex(PortableAIContextError, "failed canonical conformance"):
            build_extractive_checkpoint(invalid)

    def test_checkpoint_does_not_use_network_or_api_environment(self):
        conversation = sample_conversation()
        with mock.patch.dict(os.environ, {"PAIC_API_KEY": "SHOULD_NOT_BE_READ"}, clear=False):
            with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("network used")):
                result = build_extractive_checkpoint(conversation, profile="lite")
        self.assertTrue(result.report.budget_met)

    def test_cli_writes_byte_identical_files_without_api_key(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.jsonl"
            source.write_text(
                json.dumps({"role": "user", "text": "Original goal."})
                + "\n"
                + json.dumps({"role": "assistant", "text": "Current status passed."})
                + "\n",
                encoding="utf-8",
            )
            out1 = root / "out-one"
            out2 = root / "out-two"

            with mock.patch.dict(os.environ, {"PAIC_API_KEY": ""}, clear=False):
                with contextlib.redirect_stdout(io.StringIO()):
                    code1 = cli_main(["checkpoint", str(source), "-o", str(out1)])
                with contextlib.redirect_stdout(io.StringIO()):
                    code2 = cli_main(["checkpoint", str(source), "-o", str(out2)])

            self.assertEqual(code1, 0)
            self.assertEqual(code2, 0)
            checkpoint1 = (out1 / "CHECKPOINT.md").read_bytes()
            checkpoint2 = (out2 / "CHECKPOINT.md").read_bytes()
            report1 = (out1 / "checkpoint-report.json").read_bytes()
            report2 = (out2 / "checkpoint-report.json").read_bytes()
            self.assertEqual(checkpoint1, checkpoint2)
            self.assertEqual(report1, report2)

            report = json.loads(report1)
            self.assertEqual(report["policy"], POLICY_VERSION)
            self.assertEqual(report["source_kind"], "jsonl")
            self.assertEqual(report["profile"], "standard")
            self.assertEqual(report["budget_tokens"], 16_000)
            self.assertTrue(report["budget_met"])
            self.assertNotIn(str(source), checkpoint1.decode("utf-8"))
            self.assertNotIn(str(source), report1.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
