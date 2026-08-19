import json
import unittest

from portable_ai_context.conformance import inspect_conformance
from portable_ai_context.models import Conversation, Message, SourceInfo


class ConformanceReportSafetyTests(unittest.TestCase):
    def test_invalid_source_kind_is_not_echoed(self):
        private_source_kind = "PRIVATE_ACCOUNT_SOURCE_KIND_DO_NOT_ECHO"
        conversation = Conversation(
            title="synthetic",
            source=SourceInfo(kind=private_source_kind),
            messages=[Message(role="user", text="safe synthetic text", index=0)],
        )

        report = inspect_conformance(conversation)
        payload = json.dumps(report.to_dict())

        self.assertFalse(report.ok)
        self.assertEqual(report.source_kind, "<invalid>")
        self.assertIn("invalid_source_kind", {item.code for item in report.violations})
        self.assertNotIn(private_source_kind, payload)


if __name__ == "__main__":
    unittest.main()
