import unittest

from portable_ai_context.checkpoint import build_extractive_checkpoint
from portable_ai_context.compiler import CallableTokenCounter
from portable_ai_context.models import Conversation, Message, SourceInfo


class CheckpointRedactionScopeTests(unittest.TestCase):
    def test_unselected_secret_does_not_count_as_checkpoint_redaction(self):
        secret = "sk-UNSELECTEDSECRETABCDEFGHIJKLMNOP"
        rendered_marker = "[REDACTED:openai_style_key]"
        message_count = 100

        def make_conversation(secret_index: int | None = None) -> Conversation:
            messages = []
            for index in range(message_count):
                role = "user" if index % 2 == 0 else "assistant"
                text = (
                    f"neutral historical evidence {index} {rendered_marker} "
                    + "context " * 24
                )
                if index == 0:
                    text = (
                        f"Original goal anchor for the deterministic checkpoint. {rendered_marker} "
                        + "goal " * 16
                    )
                elif index == 2:
                    text = (
                        f"下一步必须继续这个未完成阻塞问题，等待验证版本提交。 {rendered_marker} "
                        + "state " * 16
                    )
                elif index == message_count - 2:
                    text = (
                        f"Latest user evidence for the current handoff. {rendered_marker} "
                        + "recent " * 20
                    )
                elif index == message_count - 1:
                    text = (
                        f"Latest assistant evidence pending final verification. {rendered_marker} "
                        + "recent " * 20
                    )

                if index == secret_index:
                    text = text.replace(rendered_marker, secret, 1)
                messages.append(Message(role=role, text=text, index=index))

            return Conversation(
                title="Redaction scope synthetic",
                source=SourceInfo(kind="synthetic"),
                messages=messages,
            )

        counter = CallableTokenCounter(
            fn=lambda text: len(text.split()),
            name="fake_exact_words",
            exact=True,
        )

        baseline = build_extractive_checkpoint(
            make_conversation(),
            budget_tokens=512,
            token_counter=counter,
        )
        unselected = [
            index
            for index in range(message_count)
            if index not in baseline.report.selected_indices
        ]
        self.assertTrue(unselected)
        secret_index = unselected[len(unselected) // 2]

        result = build_extractive_checkpoint(
            make_conversation(secret_index),
            budget_tokens=512,
            token_counter=counter,
        )

        # The fake secret redacts to the exact literal marker used in the
        # baseline source, so prepared text and therefore selection stay equal.
        self.assertEqual(result.report.selected_indices, baseline.report.selected_indices)
        self.assertNotIn(secret_index, result.report.selected_indices)
        self.assertEqual(result.report.redaction_counts["openai_style_key"], 0)
        self.assertNotIn(secret, result.markdown)


if __name__ == "__main__":
    unittest.main()
