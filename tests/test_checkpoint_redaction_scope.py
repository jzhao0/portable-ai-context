import unittest

from portable_ai_context.checkpoint import build_extractive_checkpoint
from portable_ai_context.compiler import CallableTokenCounter
from portable_ai_context.models import Conversation, Message, SourceInfo


class CheckpointRedactionScopeTests(unittest.TestCase):
    def test_unselected_secret_does_not_count_as_checkpoint_redaction(self):
        secret = "sk-UNSELECTEDSECRETABCDEFGHIJKLMNOP"
        secret_index = 5
        message_count = 100
        messages = []
        for index in range(message_count):
            role = "user" if index % 2 == 0 else "assistant"
            text = f"neutral historical evidence {index} " + "context " * 24
            if index == 0:
                text = "Original goal anchor for the deterministic checkpoint. " + "goal " * 16
            elif index == 2:
                text = "下一步必须继续这个未完成阻塞问题，等待验证版本提交。 " + "state " * 16
            elif index == secret_index:
                text = f"old unselected credential {secret} " + "old " * 24
            elif index == message_count - 2:
                text = "Latest user evidence for the current handoff. " + "recent " * 20
            elif index == message_count - 1:
                text = "Latest assistant evidence pending final verification. " + "recent " * 20
            messages.append(Message(role=role, text=text, index=index))

        conversation = Conversation(
            title="Redaction scope synthetic",
            source=SourceInfo(kind="synthetic"),
            messages=messages,
        )
        counter = CallableTokenCounter(
            fn=lambda text: len(text.split()),
            name="fake_exact_words",
            exact=True,
        )
        result = build_extractive_checkpoint(
            conversation,
            budget_tokens=512,
            token_counter=counter,
        )

        # The old credential sits far outside the bounded recent-fill horizon.
        # This verifies report semantics without changing the selection policy.
        self.assertNotIn(secret_index, result.report.selected_indices)
        self.assertLess(len(result.report.selected_indices), message_count)
        self.assertEqual(result.report.redaction_counts["openai_style_key"], 0)
        self.assertNotIn(secret, result.markdown)


if __name__ == "__main__":
    unittest.main()
