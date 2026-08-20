from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from _helpers import sample_conversation
from portable_ai_context.adapters import load_conversation
from portable_ai_context.bundle_contract import (
    AICB_MEMBER_ORDER,
    AICB_REQUIRED_MEMBERS,
    AICB_SCHEMA_VERSION,
)
from portable_ai_context.exporters import write_bundle
from portable_ai_context.integrity import inspect as inspect_integrity


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "aicb_0_1_alpha_golden.aicb.b64"
SCHEMA = ROOT / "schemas" / "conversation-bundle.schema.json"

GOLDEN_BUNDLE_SHA256 = "3db7230deb0c3b665380895d9acbed044e494282595039fb75e1d751bb4e099e"
GOLDEN_CONVERSATION_DIGEST = "fbe519c91e833b034a7dae92e0802afc86b29bf3670beb365cf8e8a1d4e3aa85"
GOLDEN_MESSAGES = [
    ("user", "Golden compatibility question."),
    ("assistant", "Golden compatibility answer."),
]


class AICBCompatibilityFloorTests(unittest.TestCase):
    def _golden_bytes(self) -> bytes:
        encoded = FIXTURE.read_text(encoding="ascii")
        return base64.b64decode(encoded, validate=False)

    def test_committed_golden_bytes_are_pinned_and_load_without_current_writer(self):
        raw = self._golden_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), GOLDEN_BUNDLE_SHA256)

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "historical-0.1-alpha.aicb"
            path.write_bytes(raw)
            loaded = load_conversation(str(path))

        self.assertEqual(loaded.title, "AICB 0.1-alpha Golden")
        self.assertEqual(
            [(message.role, message.text) for message in loaded.messages],
            GOLDEN_MESSAGES,
        )
        self.assertEqual(
            inspect_integrity(loaded).conversation_digest,
            GOLDEN_CONVERSATION_DIGEST,
        )
        self.assertEqual(loaded.source.kind, "aicb")
        self.assertEqual(
            loaded.source.metadata["bundle_schema_version"],
            "0.1-alpha",
        )
        self.assertEqual(
            loaded.source.metadata["bundle_original_source_kind"],
            "synthetic",
        )
        self.assertIs(loaded.source.metadata["bundle_integrity_verified"], True)
        self.assertEqual(loaded.source.fingerprint, GOLDEN_BUNDLE_SHA256)

    def test_golden_archive_member_set_is_exact(self):
        raw = self._golden_bytes()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "historical.aicb"
            path.write_bytes(raw)
            with zipfile.ZipFile(path, "r") as archive:
                names = tuple(info.filename for info in archive.infolist())
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

        self.assertEqual(names, AICB_MEMBER_ORDER)
        self.assertEqual(frozenset(names), AICB_REQUIRED_MEMBERS)
        self.assertEqual(manifest["schema_version"], AICB_SCHEMA_VERSION)
        self.assertEqual(tuple(manifest["artifacts"]), AICB_MEMBER_ORDER)
        self.assertEqual(manifest["created_at"], "2026-08-20T00:00:00+00:00")

    def test_json_schema_tracks_runtime_bundle_contract(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(
            schema["properties"]["schema_version"]["const"],
            AICB_SCHEMA_VERSION,
        )
        artifact_schema = schema["properties"]["artifacts"]
        self.assertEqual(
            set(artifact_schema["items"]["enum"]),
            set(AICB_REQUIRED_MEMBERS),
        )
        self.assertEqual(artifact_schema["minItems"], len(AICB_REQUIRED_MEMBERS))
        self.assertEqual(artifact_schema["maxItems"], len(AICB_REQUIRED_MEMBERS))

    def test_current_writer_uses_shared_runtime_contract(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "current.aicb"
            write_bundle(sample_conversation(), path)
            with zipfile.ZipFile(path, "r") as archive:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                names = tuple(info.filename for info in archive.infolist())

        self.assertEqual(manifest["schema_version"], AICB_SCHEMA_VERSION)
        self.assertEqual(tuple(manifest["artifacts"]), AICB_MEMBER_ORDER)
        self.assertEqual(names, AICB_MEMBER_ORDER)

    def test_runtime_version_literal_has_one_code_source(self):
        bundle_contract = (
            ROOT / "src" / "portable_ai_context" / "bundle_contract.py"
        ).read_text(encoding="utf-8")
        reader = (
            ROOT / "src" / "portable_ai_context" / "adapters" / "aicb.py"
        ).read_text(encoding="utf-8")
        writer = (
            ROOT / "src" / "portable_ai_context" / "exporters.py"
        ).read_text(encoding="utf-8")

        self.assertIn('AICB_SCHEMA_VERSION = "0.1-alpha"', bundle_contract)
        self.assertNotIn('"0.1-alpha"', reader)
        self.assertNotIn('"0.1-alpha"', writer)


if __name__ == "__main__":
    unittest.main()
