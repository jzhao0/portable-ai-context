import json
import tempfile
from pathlib import Path
import unittest

from portable_ai_context.adapters import gemini_activity_json
from portable_ai_context.adapters.registry import load_conversation
from portable_ai_context.errors import ParseError
from portable_ai_context.exporters import write_standard


FIXTURE = Path(__file__).parent / "fixtures" / "gemini_my_activity.synthetic.json"


class GeminiActivityJsonAdapterTests(unittest.TestCase):
    def test_fixture_is_recognized_sorted_and_canonicalized(self):
        text = FIXTURE.read_text(encoding="utf-8")
        self.assertTrue(gemini_activity_json.can_load(text))

        conv = gemini_activity_json.load(str(FIXTURE), text)
        self.assertEqual(conv.title, "Gemini Apps")
        self.assertEqual(conv.source.kind, "gemini_my_activity_json")
        self.assertEqual(conv.source.metadata["format"], "google_my_activity_gemini_json")
        self.assertEqual(conv.source.metadata["source_record_count"], 3)
        self.assertEqual(conv.source.metadata["activity_record_count"], 2)
        self.assertEqual(conv.snapshot.raw_node_count, 2)
        self.assertIsNotNone(conv.snapshot.created_at)
        self.assertIsNotNone(conv.snapshot.updated_at)
        self.assertEqual(conv.snapshot.updated_at - conv.snapshot.created_at, 300.0)
        self.assertEqual(
            conv.snapshot.metadata["thread_reconstruction"],
            "not_available_from_supported_activity_stream",
        )

        self.assertEqual(
            [m.role for m in conv.messages],
            ["user", "assistant", "user", "assistant"],
        )
        self.assertEqual(
            [m.text for m in conv.messages],
            [
                "Build a privacy-safe Gemini activity adapter.",
                "The Gemini activity adapter is implemented.\nOnly supported text crosses the boundary.",
                "Verify the Gemini adapter tail.",
                "Tail verification passed.\n2/2 messages preserved",
            ],
        )
        self.assertEqual([m.index for m in conv.messages], [0, 1, 2, 3])
        self.assertEqual(conv.messages[-2].text, "Verify the Gemini adapter tail.")
        self.assertEqual(conv.messages[-1].text, "Tail verification passed.\n2/2 messages preserved")

    def test_runtime_account_attachment_and_non_gemini_fields_do_not_cross_boundary(self):
        conv = load_conversation(str(FIXTURE))
        canonical = json.dumps(conv.to_dict(), ensure_ascii=False)

        for forbidden in [
            "PRIVATE_GEMINI_ACCOUNT@example.invalid",
            "PRIVATE_GEMINI_USER_ID",
            "PRIVATE_GEMINI_SESSION_TOKEN",
            "PRIVATE_LOCATION",
            "PRIVATE_ATTACHMENT.bin",
            "PRIVATE_ACTIVITY_CONTROL",
            "private-gemini-url",
            "PRIVATE_RUNTIME_DETAIL",
            "PRIVATE_AUDIO.m4a",
            "PRIVATE_IMAGE.webp",
            "PRIVATE_AUTHORIZATION_VALUE",
            "PRIVATE_NON_GEMINI_PROMPT",
            "PRIVATE_NON_GEMINI_RESPONSE",
        ]:
            self.assertNotIn(forbidden, canonical)

    def test_single_activity_record_is_supported(self):
        record = {
            "header": "Gemini Apps",
            "products": ["Gemini Apps"],
            "title": "Prompted: Question",
            "time": "2026-08-18T12:00:00Z",
            "safeHtmlItem": [{"html": "<p>Answer</p>"}],
        }
        text = json.dumps(record)
        self.assertTrue(gemini_activity_json.can_load(text))
        conv = gemini_activity_json.load("single.json", text)
        self.assertEqual([(m.role, m.text) for m in conv.messages], [("user", "Question"), ("assistant", "Answer")])

    def test_non_gemini_activity_is_not_recognized(self):
        text = json.dumps(
            [
                {
                    "header": "Search",
                    "products": ["Search"],
                    "title": "Prompted private text",
                    "safeHtmlItem": [{"html": "<p>private response</p>"}],
                }
            ]
        )
        self.assertFalse(gemini_activity_json.can_load(text))
        with self.assertRaisesRegex(ParseError, "no Gemini Apps activity records"):
            gemini_activity_json.load("search.json", text)

    def test_missing_timestamps_preserve_source_order_after_timestamped_records(self):
        records = [
            {
                "header": "Gemini Apps",
                "products": ["Gemini Apps"],
                "title": "Prompted no-time-first",
                "safeHtmlItem": [{"html": "<p>response-one</p>"}],
            },
            {
                "header": "Gemini Apps",
                "products": ["Gemini Apps"],
                "title": "Prompted timestamped",
                "time": "2026-08-18T11:00:00Z",
                "safeHtmlItem": [{"html": "<p>response-two</p>"}],
            },
            {
                "header": "Gemini Apps",
                "products": ["Gemini Apps"],
                "title": "Prompted no-time-second",
                "safeHtmlItem": [{"html": "<p>response-three</p>"}],
            },
        ]
        conv = gemini_activity_json.load("mixed.json", json.dumps(records))
        self.assertEqual(
            [m.text for m in conv.messages],
            [
                "timestamped",
                "response-two",
                "no-time-first",
                "response-one",
                "no-time-second",
                "response-three",
            ],
        )
        self.assertEqual(conv.snapshot.metadata["missing_timestamp_records"], 2)

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
