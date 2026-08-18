import json
import tempfile
from pathlib import Path
import unittest

from portable_ai_context.adapters import claude_json
from portable_ai_context.adapters.registry import load_conversation
from portable_ai_context.errors import ParseError
from portable_ai_context.exporters import write_standard


FIXTURE = Path(__file__).parent / "fixtures" / "claude_conversation.synthetic.json"


class ClaudeJsonAdapterTests(unittest.TestCase):
    def test_fixture_is_recognized_and_canonicalized_in_order(self):
        text = FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(claude_json.can_load(text))

        conv = claude_json.load(str(FIXTURE), text)
        self.assertEqual(conv.title, "Synthetic Claude Project")
        self.assertEqual(conv.source.kind, "claude_json")
        self.assertEqual(conv.source.metadata["format"], "claude_conversation_json")
        self.assertEqual(conv.snapshot.raw_node_count, 5)
        self.assertIsNotNone(conv.snapshot.created_at)
        self.assertIsNotNone(conv.snapshot.updated_at)
        self.assertEqual(conv.snapshot.updated_at - conv.snapshot.created_at, 300.0)

        self.assertEqual(
            [m.role for m in conv.messages],
            ["user", "assistant", "user", "assistant"],
        )
        self.assertEqual(
            [m.text for m in conv.messages],
            [
                "Build the portable context adapter.",
                "The adapter is implemented.",
                "Verify the privacy boundary.",
                "Privacy boundary verified.",
            ],
        )
        self.assertEqual(conv.messages[-2].text, "Verify the privacy boundary.")
        self.assertEqual(conv.messages[-1].text, "Privacy boundary verified.")
        self.assertEqual([m.index for m in conv.messages], [0, 1, 2, 3])

    def test_runtime_account_and_non_text_fields_do_not_cross_boundary(self):
        conv = load_conversation(str(FIXTURE))
        canonical = json.dumps(conv.to_dict(), ensure_ascii=False)

        for forbidden in [
            "PRIVATE_ACCOUNT@example.invalid",
            "PRIVATE_USER_ID",
            "PRIVATE_ORG_ID",
            "PRIVATE_SESSION_TOKEN",
            "PRIVATE_REASONING_BLOCK",
            "PRIVATE_TOOL_TOKEN",
            "PRIVATE_SYSTEM_RUNTIME_MESSAGE",
            "private-runtime-model",
            "private-attachment",
        ]:
            self.assertNotIn(forbidden, canonical)

    def test_multiple_conversations_are_rejected_explicitly(self):
        record = {
            "name": "one",
            "chat_messages": [
                {"sender": "human", "text": "hello"},
                {"sender": "assistant", "text": "hi"},
            ],
        }
        text = json.dumps([record, {**record, "name": "two"}])
        self.assertTrue(claude_json.can_load(text))
        with self.assertRaisesRegex(ParseError, "multiple conversation records"):
            claude_json.load("conversations.json", text)

    def test_single_record_list_and_wrapper_are_supported(self):
        record = {
            "title": "Wrapped Claude",
            "chat_messages": [
                {"sender": "user", "content": [{"type": "text", "text": "Question"}]},
                {"sender": "assistant", "text": "Answer"},
            ],
        }
        for value in ([record], {"conversations": [record]}):
            with self.subTest(root_type=type(value).__name__):
                conv = claude_json.load("single.json", json.dumps(value))
                self.assertEqual(conv.title, "Wrapped Claude")
                self.assertEqual([m.text for m in conv.messages], ["Question", "Answer"])

    def test_roundtrip_through_standard_clean_outputs_without_message_loss(self):
        original = load_conversation(str(FIXTURE))
        with tempfile.TemporaryDirectory() as td:
            paths = write_standard(original, td)
            for key in ["clean_html", "compact_txt", "jsonl"]:
                with self.subTest(format=key):
                    loaded = load_conversation(str(paths[key]))
                    self.assertEqual(
                        [(m.role, m.text) for m in loaded.messages],
                        [(m.role, m.text) for m in original.messages],
                    )


if __name__ == "__main__":
    unittest.main()
