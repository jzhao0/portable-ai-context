import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from portable_ai_context.adapters import load_conversation
from portable_ai_context.checkpoint import build_extractive_checkpoint
from portable_ai_context.cli import main as cli_main
from portable_ai_context.errors import PortableAIContextError
from portable_ai_context.integrity import inspect as inspect_integrity
from portable_ai_context.models import Conversation, Message, SourceInfo
from portable_ai_context.privacy import BODY_PATTERNS, redact_body_text
from portable_ai_context.redaction import (
    DERIVED_TITLE,
    build_redaction_review,
    write_redaction_review,
)


OPENAI_KEY = "sk-ABCDEFGHIJKLMNOPQRSTUVWX"
GITHUB_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
AWS_KEY = "AKIAABCDEFGHIJKLMNOP"
BEARER = "Bearer abcdefghijklmnopqrstuvwxyz0123456789"
PRIVATE_KEY_BLOCK = """-----BEGIN PRIVATE KEY-----
PRIVATE_KEY_BODY_SHOULD_NOT_SURVIVE
-----END PRIVATE KEY-----"""
PRIVATE_TITLE = "PRIVATE_TITLE_SHOULD_NOT_SURVIVE"
PRIVATE_LOCATOR = "/Users/private/PRIVATE_SOURCE_PATH.json"
ORDINARY = "ordinary nonmatching text should remain unchanged"


def _conversation() -> Conversation:
    return Conversation(
        title=PRIVATE_TITLE,
        source=SourceInfo(
            kind="jsonl",
            locator=PRIVATE_LOCATOR,
            metadata={"PRIVATE_METADATA": "PRIVATE_METADATA_VALUE"},
        ),
        messages=[
            Message(
                role="user",
                index=0,
                text=(
                    f"{ORDINARY}\n"
                    f"openai={OPENAI_KEY}\n"
                    f"github={GITHUB_TOKEN}\n"
                    f"aws={AWS_KEY}\n"
                    f"auth={BEARER}"
                ),
                metadata={"PRIVATE_MESSAGE_METADATA": "PRIVATE_MESSAGE_METADATA_VALUE"},
            ),
            Message(
                role="assistant",
                index=1,
                text=f"key block:\n{PRIVATE_KEY_BLOCK}\n{ORDINARY}",
            ),
        ],
        metadata={"PRIVATE_CONVERSATION_METADATA": "PRIVATE_CONVERSATION_METADATA_VALUE"},
    )


class RedactBodyTextTests(unittest.TestCase):
    def test_supported_patterns_are_redacted_without_returning_values(self):
        text = (
            f"{OPENAI_KEY}\n{GITHUB_TOKEN}\n{AWS_KEY}\n{BEARER}\n"
            f"{PRIVATE_KEY_BLOCK}\n{ORDINARY}"
        )
        redacted, counts = redact_body_text(text)

        for secret in (
            OPENAI_KEY,
            GITHUB_TOKEN,
            AWS_KEY,
            BEARER,
            "PRIVATE_KEY_BODY_SHOULD_NOT_SURVIVE",
        ):
            self.assertNotIn(secret, redacted)
        self.assertIn(ORDINARY, redacted)
        self.assertEqual(counts["openai_style_key"], 1)
        self.assertEqual(counts["github_token"], 1)
        self.assertEqual(counts["aws_access_key"], 1)
        self.assertEqual(counts["bearer_token"], 1)
        self.assertEqual(counts["private_key_material"], 1)
        # The whole private-key material rule intentionally runs before the
        # header-only detector, preserving the checkpoint's historical counts.
        self.assertEqual(counts["private_key_header"], 0)
        self.assertEqual(set(BODY_PATTERNS), set(counts) - {"private_key_material"})

    def test_multiple_nearby_matches_are_counted_deterministically(self):
        text = f"{OPENAI_KEY} {OPENAI_KEY}\n{GITHUB_TOKEN} {GITHUB_TOKEN}"
        redacted, counts = redact_body_text(text)
        self.assertEqual(counts["openai_style_key"], 2)
        self.assertEqual(counts["github_token"], 2)
        self.assertEqual(redacted.count("[REDACTED:openai_style_key]"), 2)
        self.assertEqual(redacted.count("[REDACTED:github_token]"), 2)


class RedactionReviewTests(unittest.TestCase):
    def test_review_is_derived_and_does_not_mutate_canonical_input(self):
        conversation = _conversation()
        before = conversation.to_dict()
        source_digest = inspect_integrity(conversation).conversation_digest

        result = build_redaction_review(conversation)

        self.assertEqual(conversation.to_dict(), before)
        self.assertEqual(
            inspect_integrity(conversation).conversation_digest,
            source_digest,
        )
        self.assertEqual(result.conversation.title, DERIVED_TITLE)
        self.assertEqual(result.conversation.source.kind, "redacted_review")
        self.assertIsNone(result.conversation.source.locator)
        self.assertEqual(result.report.source_conversation_digest, source_digest)
        self.assertNotEqual(
            result.report.redacted_conversation_digest,
            source_digest,
        )
        self.assertEqual(result.report.affected_message_count, 2)
        self.assertEqual(result.report.supported_patterns_remaining, 0)
        self.assertIs(result.report.manual_review_required, True)
        self.assertIs(result.report.patterns_are_exhaustive, False)
        self.assertIs(result.report.original_title_preserved, False)
        self.assertIs(result.report.source_locator_preserved, False)

    def test_report_is_content_free_and_does_not_embed_private_fields(self):
        result = build_redaction_review(_conversation())
        serialized = json.dumps(result.report.to_dict(), sort_keys=True)

        for private_value in (
            OPENAI_KEY,
            GITHUB_TOKEN,
            AWS_KEY,
            BEARER,
            "PRIVATE_KEY_BODY_SHOULD_NOT_SURVIVE",
            PRIVATE_TITLE,
            PRIVATE_LOCATOR,
            "PRIVATE_METADATA_VALUE",
            "PRIVATE_MESSAGE_METADATA_VALUE",
            "PRIVATE_CONVERSATION_METADATA_VALUE",
            ORDINARY,
        ):
            self.assertNotIn(private_value, serialized)

        self.assertIn("source_message_sha256", serialized)
        self.assertIn("source_conversation_digest", serialized)
        self.assertIn("redacted_conversation_digest", serialized)
        self.assertIn("redaction_counts", serialized)

    def test_written_formats_round_trip_to_same_redacted_digest(self):
        conversation = _conversation()
        result = build_redaction_review(conversation)
        with tempfile.TemporaryDirectory() as td:
            paths = write_redaction_review(conversation, td)
            loaded = [
                load_conversation(paths["redacted_clean_html"]),
                load_conversation(paths["redacted_compact_txt"]),
                load_conversation(paths["redacted_jsonl"]),
            ]
            report = json.loads(
                paths["redaction_report"].read_text(encoding="utf-8")
            )

        digests = [inspect_integrity(item).conversation_digest for item in loaded]
        self.assertEqual(
            digests,
            [result.report.redacted_conversation_digest] * 3,
        )
        self.assertEqual(
            report["redacted_conversation_digest"],
            result.report.redacted_conversation_digest,
        )
        self.assertEqual(report["supported_patterns_remaining"], 0)
        self.assertIs(report["manual_review_required"], True)
        self.assertIs(report["patterns_are_exhaustive"], False)

    def test_checkpoint_and_explicit_review_share_redaction_semantics(self):
        conversation = Conversation(
            title="test",
            source=SourceInfo(kind="jsonl"),
            messages=[
                Message(
                    role="user",
                    index=0,
                    text=f"next action keep this secret {OPENAI_KEY}",
                ),
                Message(role="assistant", index=1, text="acknowledged"),
            ],
        )
        review = build_redaction_review(conversation)
        checkpoint = build_extractive_checkpoint(
            conversation,
            budget_tokens=4000,
        )

        self.assertIn("[REDACTED:openai_style_key]", review.conversation.messages[0].text)
        self.assertIn("[REDACTED:openai_style_key]", checkpoint.markdown)
        self.assertEqual(review.report.total_redaction_counts["openai_style_key"], 1)
        self.assertEqual(checkpoint.report.redaction_counts["openai_style_key"], 1)
        self.assertNotIn(OPENAI_KEY, checkpoint.markdown)

    def test_invalid_canonical_structure_fails_with_content_free_error(self):
        conversation = Conversation(
            title=PRIVATE_TITLE,
            source=SourceInfo(kind="PRIVATE/UNSAFE"),
            messages=[Message(role="system", index=7, text=OPENAI_KEY)],
        )
        with self.assertRaises(PortableAIContextError) as caught:
            build_redaction_review(conversation)
        message = str(caught.exception)
        self.assertIn("failed canonical structure", message)
        self.assertNotIn(PRIVATE_TITLE, message)
        self.assertNotIn(OPENAI_KEY, message)
        self.assertNotIn("PRIVATE/UNSAFE", message)


class RedactionCliTests(unittest.TestCase):
    def test_cli_redact_outputs_content_free_summary_and_derived_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.jsonl"
            source.write_text(
                json.dumps({"role": "user", "text": f"secret={OPENAI_KEY}"})
                + "\n"
                + json.dumps({"role": "assistant", "text": ORDINARY})
                + "\n",
                encoding="utf-8",
            )
            out = root / "review"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli_main(["redact", str(source), "-o", str(out)])
            payload = json.loads(stdout.getvalue())

            self.assertEqual(code, 0)
            self.assertEqual(payload["summary"]["affected_message_count"], 1)
            self.assertEqual(payload["summary"]["supported_patterns_remaining"], 0)
            self.assertIs(payload["summary"]["manual_review_required"], True)
            self.assertTrue((out / "conversation.redacted.clean.html").is_file())
            self.assertTrue((out / "conversation.redacted.compact.txt").is_file())
            self.assertTrue((out / "conversation.redacted.jsonl").is_file())
            self.assertTrue((out / "redaction-report.json").is_file())

            combined_stdout = stdout.getvalue()
            self.assertNotIn(OPENAI_KEY, combined_stdout)
            report_text = (out / "redaction-report.json").read_text(encoding="utf-8")
            self.assertNotIn(OPENAI_KEY, report_text)


if __name__ == "__main__":
    unittest.main()
