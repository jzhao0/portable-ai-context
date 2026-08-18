import unittest

from portable_ai_context.integrity import inspect as inspect_integrity
from portable_ai_context.privacy import inspect_conversation
from portable_ai_context.models import Conversation, Message, SourceInfo
from _helpers import sample_conversation


class IntegrityPrivacyTests(unittest.TestCase):
    def test_integrity_is_deterministic(self):
        conv = sample_conversation()
        a = inspect_integrity(conv)
        b = inspect_integrity(conv)
        self.assertEqual(a.conversation_digest, b.conversation_digest)
        self.assertEqual(a.message_count, 4)
        self.assertEqual(a.user_count, 2)
        self.assertEqual(a.assistant_count, 2)

    def test_secret_scanner_counts_without_returning_values(self):
        secret = "sk-ABCDEFGHIJKLMNOPQRSTUVWX"
        conv = Conversation(
            title="secret test",
            messages=[Message(role="user", text=f"key={secret}", index=0)],
            source=SourceInfo(kind="synthetic"),
        )
        report = inspect_conversation(conv)
        self.assertEqual(report.body_secret_counts["openai_style_key"], 1)
        self.assertFalse(report.safe_to_share_automatically)
        self.assertNotIn(secret, str(report.to_dict()))


if __name__ == "__main__":
    unittest.main()
