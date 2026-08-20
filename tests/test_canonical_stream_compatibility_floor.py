from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from portable_ai_context.adapters import load_conversation
from portable_ai_context.adapters import jsonl as jsonl_adapter
from portable_ai_context.canonical_contract import (
    CANONICAL_MESSAGE_FIELDS,
    CANONICAL_ROLE_ORDER,
    CANONICAL_ROLES,
)
from portable_ai_context.conformance import inspect_conformance
from portable_ai_context.exporters import jsonl as export_jsonl
from portable_ai_context.integrity import inspect as inspect_integrity


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "canonical_role_text_golden.jsonl"

GOLDEN_FILE_SHA256 = "381db70fa84c54bb56d64847f695c2784dbfb2f8f3127bc4d9ed2ff620f63414"
GOLDEN_CONVERSATION_DIGEST = "a16d8e5671b80e1b5f771879dfc223c890883977087cd58c555bb47c5e8f64a4"
GOLDEN_MESSAGES = [
    ("user", "Golden canonical question."),
    ("assistant", "Golden canonical answer."),
    ("user", "Golden canonical follow-up.\nLine two."),
    ("assistant", "Golden canonical final."),
]


class CanonicalStreamCompatibilityFloorTests(unittest.TestCase):
    def test_committed_historical_jsonl_bytes_are_pinned(self):
        raw = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), GOLDEN_FILE_SHA256)

    def test_gitattributes_pins_historical_jsonl_to_lf_on_every_checkout(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn(
            "tests/fixtures/canonical_role_text_golden.jsonl text eol=lf",
            attributes,
        )
        raw = FIXTURE.read_bytes()
        self.assertNotIn(b"\r\n", raw)

    def test_historical_jsonl_loads_without_current_exporter_generation(self):
        conversation = load_conversation(str(FIXTURE))
        self.assertEqual(conversation.source.kind, "jsonl")
        self.assertEqual(
            [(message.role, message.text) for message in conversation.messages],
            GOLDEN_MESSAGES,
        )
        self.assertEqual(
            inspect_integrity(conversation).conversation_digest,
            GOLDEN_CONVERSATION_DIGEST,
        )

    def test_historical_jsonl_passes_current_canonical_conformance(self):
        conversation = load_conversation(str(FIXTURE))
        report = inspect_conformance(
            conversation,
            expected_messages=GOLDEN_MESSAGES,
        )
        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(report.conversation_digest, GOLDEN_CONVERSATION_DIGEST)
        self.assertTrue(report.checks["canonical_roles"])
        self.assertTrue(report.checks["contiguous_indices"])
        self.assertTrue(report.checks["nonempty_text"])
        self.assertTrue(report.checks["roundtrip_jsonl"])

    def test_current_jsonl_export_records_are_exactly_narrow_canonical_shape(self):
        conversation = load_conversation(str(FIXTURE))
        text = export_jsonl(conversation)
        records = [json.loads(line) for line in text.splitlines() if line.strip()]

        self.assertEqual(len(records), len(GOLDEN_MESSAGES))
        for record in records:
            self.assertEqual(set(record), CANONICAL_MESSAGE_FIELDS)
            self.assertIn(record["role"], CANONICAL_ROLES)
            self.assertIsInstance(record["text"], str)
            self.assertTrue(record["text"].strip())

        self.assertEqual(
            [(record["role"], record["text"]) for record in records],
            GOLDEN_MESSAGES,
        )

    def test_generic_jsonl_ingestion_remains_tolerant_of_extra_and_irrelevant_records(self):
        source = "\n".join(
            [
                json.dumps({"role": "system", "text": "ignored system"}),
                json.dumps({"role": "user", "text": "kept user", "extra": "ignored metadata"}),
                json.dumps(["ignored non-object"]),
                json.dumps({"role": "assistant", "text": "   "}),
                json.dumps({"role": "assistant", "text": "kept assistant", "future": 1}),
            ]
        )
        conversation = jsonl_adapter.load("tolerant.jsonl", source)
        self.assertEqual(
            [(message.role, message.text) for message in conversation.messages],
            [("user", "kept user"), ("assistant", "kept assistant")],
        )

    def test_runtime_contract_has_expected_existing_semantics(self):
        self.assertEqual(CANONICAL_ROLE_ORDER, ("user", "assistant"))
        self.assertEqual(CANONICAL_ROLES, frozenset({"user", "assistant"}))
        self.assertEqual(CANONICAL_MESSAGE_FIELDS, frozenset({"role", "text"}))

    def test_strict_runtime_paths_reference_shared_contract(self):
        exporter = (ROOT / "src" / "portable_ai_context" / "exporters.py").read_text(
            encoding="utf-8"
        )
        aicb = (
            ROOT / "src" / "portable_ai_context" / "adapters" / "aicb.py"
        ).read_text(encoding="utf-8")
        conformance = (
            ROOT / "src" / "portable_ai_context" / "conformance.py"
        ).read_text(encoding="utf-8")
        jsonl_source = (
            ROOT / "src" / "portable_ai_context" / "adapters" / "jsonl.py"
        ).read_text(encoding="utf-8")

        self.assertIn("canonical_message_record", exporter)
        self.assertIn("CANONICAL_MESSAGE_FIELDS", aicb)
        self.assertIn("CANONICAL_ROLES", aicb)
        self.assertIn("CANONICAL_ROLES", conformance)
        self.assertIn("CANONICAL_ROLES", jsonl_source)


if __name__ == "__main__":
    unittest.main()
