import unittest

from portable_ai_context.adapters import compact_txt as compact_txt_adapter
from portable_ai_context.conformance import inspect_conformance
from portable_ai_context.exporters import compact_txt
from portable_ai_context.models import Conversation, Message, SourceInfo
from portable_ai_context.utils import normalize_text


class CompactTxtRoundTripTests(unittest.TestCase):
    def test_exported_marker_lines_and_existing_backslashes_round_trip(self):
        conversation = Conversation(
            title="Marker collision synthetic",
            source=SourceInfo(kind="synthetic"),
            messages=[
                Message(
                    role="user",
                    text="before\n<<<USER>>>\n<<<USER>>\n\\<<<ASSISTANT>>>\nafter",
                    index=0,
                ),
                Message(
                    role="assistant",
                    text="literal assistant marker follows\n<<<ASSISTANT>>>\ndone",
                    index=1,
                ),
            ],
        )

        exported = compact_txt(conversation)
        self.assertIn("FORMAT: paic-compact-v1", exported)
        self.assertIn("\\<<<USER>>>", exported)
        self.assertIn("<<<USER>>", exported)
        self.assertIn("\\\\<<<ASSISTANT>>>", exported)

        loaded = compact_txt_adapter.load("roundtrip.txt", exported)
        self.assertEqual(
            [(message.role, message.text) for message in loaded.messages],
            [
                (message.role, normalize_text(message.text))
                for message in conversation.messages
            ],
        )
        self.assertEqual(loaded.source.metadata["format"], "paic-compact-v1")

        report = inspect_conformance(conversation)
        self.assertTrue(report.ok, report.to_dict())
        self.assertTrue(report.checks["roundtrip_compact_txt"])

    def test_legacy_marker_text_without_format_header_still_loads(self):
        legacy = """TITLE: Legacy\nMESSAGES: 2\nPOLICY: old marker format\n\n<<<USER>>>\nlegacy question\n\n<<<ASSISTANT>>>\nlegacy answer\n"""
        loaded = compact_txt_adapter.load("legacy.txt", legacy)
        self.assertEqual(
            [(message.role, message.text) for message in loaded.messages],
            [("user", "legacy question"), ("assistant", "legacy answer")],
        )
        self.assertEqual(loaded.source.metadata["format"], "legacy-marker-text")

    def test_legacy_tolerance_does_not_change_strict_v1_marker_rules(self):
        legacy = """TITLE: Legacy tolerant\n\n<<<USER>>\nlegacy two-close marker\n\n<<<ASSISTANT>>\nlegacy answer\n"""
        loaded = compact_txt_adapter.load("legacy-tolerant.txt", legacy)
        self.assertEqual(len(loaded.messages), 2)
        self.assertEqual(loaded.messages[0].text, "legacy two-close marker")


if __name__ == "__main__":
    unittest.main()
