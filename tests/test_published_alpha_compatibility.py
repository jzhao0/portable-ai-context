from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from _helpers import sample_conversation
from portable_ai_context.adapters import aicb, load_conversation
from portable_ai_context.cli import main as cli_main
from portable_ai_context.exporters import write_bundle
from portable_ai_context.integrity import inspect as inspect_integrity


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "compat" / "v0.1.0a2-aicb"
SCHEMA = ROOT / "schemas" / "conversation-bundle.schema.json"
ROADMAP = ROOT / "ROADMAP.md"

EXPECTED_MEMBER_SHA256 = {
    "manifest.json": "72012f1f55ba553630cb0cf57b1cf4edc5ee0ebe4be357df4ec6173553552ee4",
    "conversation.jsonl": "1015bbb05b825f34b26b8ddb6af1dc8dd6982f90fd906a6ad43cb594f0a68812",
    "integrity.json": "7a8e4e18bbe6c1f66b28de020a31459ab261b2772c7830d71788a7128a79e652",
    "privacy.json": "6fcaa6f5552bab823bfd01dfc33280f75cf6e595df3ab447731e4f3157f115ef",
}
EXPECTED_TITLE = "Published 0.1.0a2 compatibility fixture"
EXPECTED_DIGEST = "a447e6a46043d4f763e3e13ac1ec00f15cb7003758c5504977ba8925aa7b1ce4"
EXPECTED_MESSAGES = [
    ("user", "Alpha compatibility fixture: first user."),
    ("assistant", "Alpha compatibility fixture: first assistant."),
    ("user", "Alpha compatibility fixture: second user."),
    ("assistant", "Alpha compatibility fixture: second assistant."),
]


class PublishedAlphaAICBCompatibilityTests(unittest.TestCase):
    def _fixture_payloads(self) -> dict[str, bytes]:
        return {
            name: (FIXTURE / name).read_bytes()
            for name in sorted(aicb.REQUIRED_MEMBERS)
        }

    def _build_historical_fixture_bundle(self, root: Path) -> Path:
        """Package fixed historical member bytes without invoking current writer."""
        output = root / "published-v0.1.0a2-contract.aicb"
        payloads = self._fixture_payloads()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(payloads):
                archive.writestr(name, payloads[name])
        return output

    def test_fixture_member_bytes_are_immutable_and_nonsecret(self):
        payloads = self._fixture_payloads()
        self.assertEqual(set(payloads), set(aicb.REQUIRED_MEMBERS))
        for name, expected_digest in EXPECTED_MEMBER_SHA256.items():
            with self.subTest(name=name):
                actual = hashlib.sha256(payloads[name]).hexdigest()
                self.assertEqual(actual, expected_digest)

        joined = b"\n".join(payloads.values())
        for forbidden in (
            b"C:\\Users\\",
            b"/Users/",
            b"/home/",
            b"@example.com",
            b"Bearer ",
            b"sk-",
            b"ghp_",
            b"AKIA",
            b"PRIVATE KEY",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, joined)

    def test_current_reader_loads_fixed_published_alpha_contract(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._build_historical_fixture_bundle(Path(td))
            loaded = load_conversation(str(bundle))
            integrity = inspect_integrity(loaded)

        self.assertEqual(loaded.source.kind, "aicb")
        self.assertEqual(loaded.source.metadata["bundle_schema_version"], "0.1-alpha")
        self.assertEqual(loaded.source.metadata["bundle_original_source_kind"], "synthetic")
        self.assertTrue(loaded.source.metadata["bundle_integrity_verified"])
        self.assertEqual(loaded.title, EXPECTED_TITLE)
        self.assertEqual(
            [(message.role, message.text) for message in loaded.messages],
            EXPECTED_MESSAGES,
        )
        self.assertEqual(integrity.conversation_digest, EXPECTED_DIGEST)
        self.assertEqual(integrity.message_count, 4)
        self.assertEqual(integrity.user_count, 2)
        self.assertEqual(integrity.assistant_count, 2)

    def test_cli_inspect_verify_and_conform_accept_fixed_published_alpha_contract(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._build_historical_fixture_bundle(Path(td))
            for command in ("inspect", "verify", "conform"):
                with self.subTest(command=command):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main([command, str(bundle)])
                    self.assertEqual(code, 0)
                    report = json.loads(stdout.getvalue())
                    if command == "inspect":
                        self.assertEqual(report["source"], "aicb")
                        self.assertEqual(report["message_count"], 4)
                        self.assertEqual(
                            report["integrity"]["conversation_digest"],
                            EXPECTED_DIGEST,
                        )
                    elif command == "verify":
                        self.assertEqual(report["conversation_digest"], EXPECTED_DIGEST)
                    else:
                        self.assertTrue(report["ok"])
                        self.assertEqual(report["source_kind"], "aicb")
                        self.assertEqual(report["message_count"], 4)

    def test_current_writer_still_emits_published_alpha_semantic_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "current-writer.aicb"
            source = sample_conversation()
            write_bundle(source, output)

            with zipfile.ZipFile(output, "r") as archive:
                names = {info.filename for info in archive.infolist()}
                self.assertEqual(names, set(aicb.REQUIRED_MEMBERS))
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                lines = [
                    json.loads(line)
                    for line in archive.read("conversation.jsonl").decode("utf-8").splitlines()
                    if line.strip()
                ]

            self.assertEqual(manifest["schema_version"], aicb.SCHEMA_VERSION)
            self.assertEqual(set(manifest), {"schema_version", "created_at", "conversation", "artifacts"})
            self.assertEqual(
                set(manifest["conversation"]),
                {"title", "message_count", "digest", "source_kind"},
            )
            self.assertEqual(set(manifest["artifacts"]), set(aicb.REQUIRED_MEMBERS))
            self.assertEqual(len(manifest["artifacts"]), len(aicb.REQUIRED_MEMBERS))
            for record in lines:
                self.assertEqual(set(record), {"role", "text"})
                self.assertIn(record["role"], {"user", "assistant"})
                self.assertIsInstance(record["text"], str)

            reopened = load_conversation(str(output))
            self.assertEqual(
                inspect_integrity(reopened).conversation_digest,
                inspect_integrity(source).conversation_digest,
            )

    def test_manifest_schema_matches_existing_reader_constraints_without_overclaiming(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], aicb.SCHEMA_VERSION)
        self.assertEqual(schema["properties"]["created_at"]["minLength"], 1)

        conversation = schema["properties"]["conversation"]
        self.assertEqual(
            set(conversation["required"]),
            {"title", "message_count", "digest", "source_kind"},
        )
        self.assertEqual(
            conversation["properties"]["digest"]["pattern"],
            "^[0-9a-f]{64}$",
        )
        self.assertEqual(
            conversation["properties"]["source_kind"]["pattern"],
            "^[a-z][a-z0-9_-]{0,63}$",
        )
        # The runtime reader currently tolerates extra manifest/conversation
        # metadata while strictly validating the fields it consumes.
        self.assertIs(schema["additionalProperties"], True)
        self.assertIs(conversation["additionalProperties"], True)

        artifacts = schema["properties"]["artifacts"]
        self.assertEqual(artifacts["minItems"], len(aicb.REQUIRED_MEMBERS))
        self.assertEqual(artifacts["maxItems"], len(aicb.REQUIRED_MEMBERS))
        self.assertIs(artifacts["uniqueItems"], True)
        self.assertEqual(set(artifacts["items"]["enum"]), set(aicb.REQUIRED_MEMBERS))

    def test_v1_stability_roadmap_items_remain_explicitly_open(self):
        roadmap = ROADMAP.read_text(encoding="utf-8")
        for line in (
            "- [ ] Stable canonical schema",
            "- [ ] Stable `.aicb` bundle format",
            "- [ ] Backward-compatibility policy",
        ):
            with self.subTest(line=line):
                self.assertIn(line, roadmap)


if __name__ == "__main__":
    unittest.main()
