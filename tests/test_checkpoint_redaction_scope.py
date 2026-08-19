import unittest

from portable_ai_context.checkpoint import (
    _SelectedMessage,
    _prepare_messages,
    _selected_redaction_counts,
)
from portable_ai_context.models import Conversation, Message, SourceInfo


class CheckpointRedactionScopeTests(unittest.TestCase):
    def test_unselected_secret_does_not_count_as_checkpoint_redaction(self):
        secret = "sk-UNSELECTEDSECRETABCDEFGHIJKLMNOP"
        conversation = Conversation(
            title="Redaction scope synthetic",
            source=SourceInfo(kind="synthetic"),
            messages=[
                Message(
                    role="user",
                    text=f"historical unselected credential {secret}",
                    index=0,
                ),
                Message(
                    role="assistant",
                    text="safe selected checkpoint evidence",
                    index=1,
                ),
            ],
        )

        prepared = _prepare_messages(conversation)
        self.assertGreater(prepared[0].redaction_counts["openai_style_key"], 0)
        self.assertEqual(prepared[1].redaction_counts["openai_style_key"], 0)

        selected = {
            1: _SelectedMessage(
                prepared=prepared[1],
                text=prepared[1].text,
                reasons=("latest_assistant",),
                truncated=False,
            )
        }
        counts = _selected_redaction_counts(selected)

        self.assertEqual(counts["openai_style_key"], 0)
        self.assertNotIn(secret, selected[1].text)

    def test_selected_secret_contributes_actual_replacement_count(self):
        secret = "sk-SELECTEDSECRETABCDEFGHIJKLMNOPQR"
        conversation = Conversation(
            title="Selected redaction scope synthetic",
            source=SourceInfo(kind="synthetic"),
            messages=[
                Message(
                    role="user",
                    text=f"selected credential {secret}",
                    index=0,
                )
            ],
        )

        prepared = _prepare_messages(conversation)
        selected = {
            0: _SelectedMessage(
                prepared=prepared[0],
                text=prepared[0].text,
                reasons=("first_user",),
                truncated=False,
            )
        }
        counts = _selected_redaction_counts(selected)

        self.assertEqual(counts["openai_style_key"], 1)
        self.assertIn("[REDACTED:openai_style_key]", selected[0].text)
        self.assertNotIn(secret, selected[0].text)


if __name__ == "__main__":
    unittest.main()
