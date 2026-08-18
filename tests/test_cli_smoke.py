import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from portable_ai_context import cli
from portable_ai_context.models import Conversation, Message, SnapshotInfo, SourceInfo


class SmokeCommandTests(unittest.TestCase):
    def test_smoke_outputs_only_non_sensitive_evidence(self):
        conversation = Conversation(
            title="PRIVATE PROJECT TITLE",
            messages=[
                Message(role="user", text="PRIVATE USER BODY", index=0),
                Message(role="assistant", text="PRIVATE ASSISTANT BODY", index=1),
            ],
            source=SourceInfo(
                kind="chatgpt_share_url",
                locator="https://chatgpt.com/share/private-link",
            ),
            snapshot=SnapshotInfo(
                updated_at=1234.5,
                raw_node_count=9,
            ),
        )

        out = io.StringIO()
        with patch.object(cli, "load_conversation", return_value=conversation), patch.object(
            cli.platform, "system", return_value="Darwin"
        ), redirect_stdout(out):
            rc = cli.main(["smoke", "ignored-source"])

        self.assertEqual(rc, 0)
        text = out.getvalue()
        payload = json.loads(text)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["platform"], "darwin")
        self.assertEqual(payload["source_kind"], "chatgpt_share_url")
        self.assertEqual(payload["message_count"], 2)
        self.assertEqual(payload["snapshot_updated_at"], 1234.5)
        self.assertEqual(payload["raw_node_count"], 9)
        self.assertEqual(len(payload["conversation_digest"]), 64)
        self.assertEqual(len(payload["last_user_hash"]), 64)
        self.assertEqual(len(payload["last_assistant_hash"]), 64)

        self.assertNotIn("PRIVATE PROJECT TITLE", text)
        self.assertNotIn("PRIVATE USER BODY", text)
        self.assertNotIn("PRIVATE ASSISTANT BODY", text)
        self.assertNotIn("private-link", text)
        self.assertNotIn("locator", payload)
        self.assertNotIn("title", payload)


if __name__ == "__main__":
    unittest.main()
