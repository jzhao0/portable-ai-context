import contextlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

from _helpers import sample_conversation
from portable_ai_context.adapters import load_conversation
from portable_ai_context.adapters import aicb
from portable_ai_context.checkpoint import build_extractive_checkpoint
from portable_ai_context.cli import main as cli_main
from portable_ai_context.conformance import inspect_conformance
from portable_ai_context.errors import ParseError
from portable_ai_context.exporters import write_bundle
from portable_ai_context.integrity import inspect as inspect_integrity
from portable_ai_context.models import Conversation, Message, SourceInfo


class AICBBundleTests(unittest.TestCase):
    def _make_bundle(self, root: Path, *, conversation=None) -> Path:
        output = root / "project.aicb"
        write_bundle(conversation or sample_conversation(), output)
        return output

    def _payloads(self, bundle: Path) -> dict[str, bytes]:
        with zipfile.ZipFile(bundle, "r") as zf:
            return {info.filename: zf.read(info) for info in zf.infolist()}

    def _rewrite(self, bundle: Path, payloads: dict[str, bytes]) -> None:
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in payloads.items():
                zf.writestr(name, data)

    def _mutate_json(self, bundle: Path, member: str, mutate) -> None:
        payloads = self._payloads(bundle)
        value = json.loads(payloads[member].decode("utf-8"))
        mutate(value)
        payloads[member] = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        self._rewrite(bundle, payloads)

    def test_bundle_is_first_class_registry_input_and_preserves_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = sample_conversation()
            source.source.locator = r"C:\Users\PRIVATE_CREATOR\secret-project\raw.html"
            bundle = self._make_bundle(root, conversation=source)

            loaded = load_conversation(str(bundle))
            original_digest = inspect_integrity(source).conversation_digest
            loaded_digest = inspect_integrity(loaded).conversation_digest

            self.assertEqual(loaded.source.kind, "aicb")
            self.assertEqual(loaded.source.metadata["bundle_schema_version"], "0.1-alpha")
            self.assertEqual(loaded.source.metadata["bundle_original_source_kind"], "synthetic")
            self.assertTrue(loaded.source.metadata["bundle_integrity_verified"])
            self.assertEqual(loaded.title, source.title)
            self.assertEqual(loaded_digest, original_digest)
            self.assertEqual(
                [(m.role, m.text, m.index) for m in loaded.messages],
                [(m.role, m.text, m.index) for m in source.messages],
            )
            self.assertNotIn("PRIVATE_CREATOR", json.dumps(loaded.source.metadata))

            conformance = inspect_conformance(
                loaded,
                forbidden_values=["PRIVATE_CREATOR", "secret-project"],
            )
            self.assertTrue(conformance.ok)
            self.assertEqual(conformance.source_kind, "aicb")

            checkpoint = build_extractive_checkpoint(loaded)
            self.assertTrue(checkpoint.report.budget_met)
            self.assertEqual(checkpoint.report.source_kind, "aicb")

    def test_inspect_verify_conform_and_checkpoint_cli_accept_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = self._make_bundle(root)

            for command in ("inspect", "verify", "conform"):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main([command, str(bundle)])
                self.assertEqual(code, 0, command)
                report = json.loads(stdout.getvalue())
                if command == "conform":
                    self.assertTrue(report["ok"])
                    self.assertEqual(report["source_kind"], "aicb")

            out = root / "checkpoint"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli_main(["checkpoint", str(bundle), "-o", str(out)])
            self.assertEqual(code, 0)
            self.assertTrue((out / "CHECKPOINT.md").is_file())
            report = json.loads((out / "checkpoint-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["source_kind"], "aicb")
            self.assertTrue(report["budget_met"])

    def test_changed_conversation_with_stale_manifest_digest_fails(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._make_bundle(Path(td))
            payloads = self._payloads(bundle)
            text = payloads["conversation.jsonl"].decode("utf-8")
            payloads["conversation.jsonl"] = text.replace("Build feature A.", "Build feature Z.").encode("utf-8")
            self._rewrite(bundle, payloads)

            with self.assertRaisesRegex(ParseError, "manifest digest does not match"):
                load_conversation(str(bundle))

    def test_manifest_message_count_tamper_fails(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._make_bundle(Path(td))
            self._mutate_json(
                bundle,
                "manifest.json",
                lambda value: value["conversation"].__setitem__("message_count", 999),
            )
            with self.assertRaisesRegex(ParseError, "manifest message count does not match"):
                load_conversation(str(bundle))

    def test_integrity_digest_and_tail_tamper_fail(self):
        for field in ("conversation_digest", "last_message_hash", "last_user_hash"):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as td:
                    bundle = self._make_bundle(Path(td))
                    self._mutate_json(
                        bundle,
                        "integrity.json",
                        lambda value, key=field: value.__setitem__(key, "0" * 64),
                    )
                    with self.assertRaisesRegex(ParseError, "integrity.json canonical field mismatch"):
                        load_conversation(str(bundle))

    def test_privacy_body_count_tamper_is_recomputed_and_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._make_bundle(Path(td))
            self._mutate_json(
                bundle,
                "privacy.json",
                lambda value: value["body_secret_counts"].__setitem__("openai_style_key", 1),
            )
            with self.assertRaisesRegex(ParseError, "body-secret counts do not match"):
                load_conversation(str(bundle))

    def test_missing_and_extra_members_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = self._make_bundle(root)
            payloads = self._payloads(bundle)
            payloads.pop("privacy.json")
            self._rewrite(bundle, payloads)
            with self.assertRaisesRegex(ParseError, "missing a required member"):
                load_conversation(str(bundle))

            bundle = self._make_bundle(root)
            payloads = self._payloads(bundle)
            payloads["extra.txt"] = b"extra"
            self._rewrite(bundle, payloads)
            with self.assertRaisesRegex(ParseError, "unexpected member"):
                load_conversation(str(bundle))

    def test_duplicate_critical_member_fails(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._make_bundle(Path(td))
            payloads = self._payloads(bundle)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for name, data in payloads.items():
                        zf.writestr(name, data)
                    zf.writestr("manifest.json", payloads["manifest.json"])
            with self.assertRaisesRegex(ParseError, "duplicate member"):
                load_conversation(str(bundle))

    def test_unsupported_schema_and_invalid_original_source_kind_fail(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = self._make_bundle(root)
            self._mutate_json(
                bundle,
                "manifest.json",
                lambda value: value.__setitem__("schema_version", "9.9"),
            )
            with self.assertRaisesRegex(ParseError, "unsupported schema version"):
                load_conversation(str(bundle))

            bundle = self._make_bundle(root)
            self._mutate_json(
                bundle,
                "manifest.json",
                lambda value: value["conversation"].__setitem__(
                    "source_kind", "../../PRIVATE_SOURCE"
                ),
            )
            with self.assertRaisesRegex(ParseError, "original source kind is not a safe identifier"):
                load_conversation(str(bundle))

    def test_malformed_json_and_jsonl_fail_without_echoing_private_content(self):
        secret = "PRIVATE_BODY_VALUE_DO_NOT_ECHO"
        conversation = Conversation(
            title="private synthetic",
            source=SourceInfo(kind="synthetic"),
            messages=[
                Message(role="user", text=secret, index=0),
                Message(role="assistant", text="safe reply", index=1),
            ],
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = self._make_bundle(root, conversation=conversation)
            payloads = self._payloads(bundle)
            payloads["manifest.json"] = b"{not-json"
            self._rewrite(bundle, payloads)
            with self.assertRaises(ParseError) as caught:
                load_conversation(str(bundle))
            self.assertNotIn(secret, str(caught.exception))

            bundle = self._make_bundle(root, conversation=conversation)
            payloads = self._payloads(bundle)
            payloads["conversation.jsonl"] = b"{not-json\n"
            self._rewrite(bundle, payloads)
            with self.assertRaises(ParseError) as caught:
                load_conversation(str(bundle))
            self.assertIn("conversation.jsonl line 1", str(caught.exception))
            self.assertNotIn(secret, str(caught.exception))

    def test_noncanonical_or_extra_jsonl_fields_fail_strict_bundle_shape(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._make_bundle(Path(td))
            payloads = self._payloads(bundle)
            first, *rest = payloads["conversation.jsonl"].decode("utf-8").splitlines()
            record = json.loads(first)
            record["runtime_secret"] = "PRIVATE_RUNTIME_VALUE"
            payloads["conversation.jsonl"] = (
                json.dumps(record) + "\n" + "\n".join(rest) + "\n"
            ).encode("utf-8")
            self._rewrite(bundle, payloads)
            with self.assertRaises(ParseError) as caught:
                load_conversation(str(bundle))
            self.assertIn("not a canonical bundle record", str(caught.exception))
            self.assertNotIn("PRIVATE_RUNTIME_VALUE", str(caught.exception))

    def test_traversal_backslash_absolute_and_nested_member_paths_fail(self):
        bad_names = (
            "../escape.txt",
            r"..\escape.txt",
            "/absolute.txt",
            "nested/extra.txt",
        )
        for bad_name in bad_names:
            with self.subTest(bad_name=bad_name):
                with tempfile.TemporaryDirectory() as td:
                    bundle = self._make_bundle(Path(td))
                    payloads = self._payloads(bundle)
                    payloads[bad_name] = b"bad"
                    self._rewrite(bundle, payloads)
                    with self.assertRaises(ParseError):
                        load_conversation(str(bundle))

    def test_symlink_like_member_fails(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._make_bundle(Path(td))
            payloads = self._payloads(bundle)
            with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for name, data in payloads.items():
                    if name == "manifest.json":
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        zf.writestr(info, data)
                    else:
                        zf.writestr(name, data)
            with self.assertRaisesRegex(ParseError, "symlink-like"):
                load_conversation(str(bundle))

    def test_archive_metadata_limits_fail_without_allocating_large_payloads(self):
        infos = []
        for name in aicb.REQUIRED_MEMBERS:
            info = zipfile.ZipInfo(name)
            info.file_size = 1
            infos.append(info)
        oversized = infos[0]
        oversized.file_size = aicb.MAX_MEMBER_BYTES + 1
        with self.assertRaisesRegex(ParseError, "member exceeds the alpha size limit"):
            aicb._validate_zip_metadata(infos)

        too_many = [zipfile.ZipInfo(f"member-{index}.txt") for index in range(aicb.MAX_MEMBER_COUNT + 1)]
        with self.assertRaisesRegex(ParseError, "too many members"):
            aicb._validate_zip_metadata(too_many)

    def test_manifest_artifact_list_must_match_archive_contract(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = self._make_bundle(Path(td))
            self._mutate_json(
                bundle,
                "manifest.json",
                lambda value: value.__setitem__(
                    "artifacts",
                    ["manifest.json", "conversation.jsonl", "integrity.json", "other.json"],
                ),
            )
            with self.assertRaisesRegex(ParseError, "artifact list does not match"):
                load_conversation(str(bundle))


if __name__ == "__main__":
    unittest.main()
