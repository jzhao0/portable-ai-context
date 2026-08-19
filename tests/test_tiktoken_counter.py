import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from portable_ai_context.cli import main as cli_main
from portable_ai_context.compiler import TiktokenTokenCounter, compile_migration
from portable_ai_context.errors import CompilerError
from portable_ai_context.models import Conversation, Message, SourceInfo


class _FakeEncoding:
    def __init__(self, name="o200k_base"):
        self.name = name
        self.inputs = []

    def encode_ordinary(self, text):
        self.inputs.append(text)
        return list(text.encode("utf-8"))


class _FakeTiktoken:
    def __init__(self):
        self.encoding = _FakeEncoding()
        self.get_calls = []
        self.model_calls = []

    def get_encoding(self, name):
        self.get_calls.append(name)
        if name == "missing_encoding":
            raise ValueError("PRIVATE_DEPENDENCY_DETAIL")
        self.encoding.name = name
        return self.encoding

    def encoding_for_model(self, model):
        self.model_calls.append(model)
        if model == "unknown-model":
            raise KeyError("PRIVATE_MODEL_LOOKUP_DETAIL")
        self.encoding.name = "o200k_base"
        return self.encoding


class TiktokenTokenCounterTests(unittest.TestCase):
    def test_explicit_encoding_wins_without_model_lookup(self):
        fake = _FakeTiktoken()
        with mock.patch(
            "portable_ai_context.compiler.budget.importlib.import_module",
            return_value=fake,
        ):
            counter = TiktokenTokenCounter(
                encoding_name="o200k_base",
                model="gpt-5-private",
            )
        self.assertEqual(fake.get_calls, ["o200k_base"])
        self.assertEqual(fake.model_calls, [])
        self.assertEqual(counter.name, "tiktoken:o200k_base")
        self.assertIs(counter.exact, True)

    def test_model_lookup_is_delegated_to_tiktoken(self):
        fake = _FakeTiktoken()
        with mock.patch(
            "portable_ai_context.compiler.budget.importlib.import_module",
            return_value=fake,
        ):
            counter = TiktokenTokenCounter(model="gpt-5-test")
        self.assertEqual(fake.model_calls, ["gpt-5-test"])
        self.assertEqual(counter.name, "tiktoken:o200k_base")

    def test_unknown_model_fails_without_echoing_dependency_detail(self):
        fake = _FakeTiktoken()
        with mock.patch(
            "portable_ai_context.compiler.budget.importlib.import_module",
            return_value=fake,
        ):
            with self.assertRaises(CompilerError) as caught:
                TiktokenTokenCounter(model="unknown-model")
        self.assertEqual(
            str(caught.exception),
            "tiktoken does not recognize the model; supply --tiktoken-encoding",
        )
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_missing_optional_dependency_has_actionable_error(self):
        with mock.patch(
            "portable_ai_context.compiler.budget.importlib.import_module",
            side_effect=ModuleNotFoundError("PRIVATE_IMPORT_DETAIL"),
        ):
            with self.assertRaises(CompilerError) as caught:
                TiktokenTokenCounter(encoding_name="o200k_base")
        self.assertEqual(
            str(caught.exception),
            "tiktoken token counter is unavailable; install portable-ai-context[tokenizers]",
        )
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_invalid_identifiers_and_missing_resolution_fail_cleanly(self):
        cases = (
            {"encoding_name": "../PRIVATE_ENCODING"},
            {"model": "PRIVATE MODEL"},
            {},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(CompilerError) as caught:
                    TiktokenTokenCounter(**kwargs)
                self.assertNotIn("PRIVATE", str(caught.exception))

    def test_encoding_failure_does_not_echo_dependency_detail(self):
        fake = _FakeTiktoken()
        with mock.patch(
            "portable_ai_context.compiler.budget.importlib.import_module",
            return_value=fake,
        ):
            with self.assertRaises(CompilerError) as caught:
                TiktokenTokenCounter(encoding_name="missing_encoding")
        self.assertEqual(str(caught.exception), "tiktoken encoding is not available")
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_counts_special_looking_and_unicode_text_as_ordinary_text(self):
        fake = _FakeTiktoken()
        with mock.patch(
            "portable_ai_context.compiler.budget.importlib.import_module",
            return_value=fake,
        ):
            counter = TiktokenTokenCounter(encoding_name="o200k_base")
        text = "<|im_start|>你好"
        self.assertEqual(counter.count(""), 0)
        self.assertEqual(counter.count(text), len(text.encode("utf-8")))
        self.assertEqual(fake.encoding.inputs, ["", text])

    def test_compilation_report_marks_tiktoken_counter_exact(self):
        fake = _FakeTiktoken()
        with mock.patch(
            "portable_ai_context.compiler.budget.importlib.import_module",
            return_value=fake,
        ):
            counter = TiktokenTokenCounter(encoding_name="o200k_base")

        conversation = Conversation(
            title="test",
            messages=[Message(role="user", text="hello", index=0)],
            source=SourceInfo(kind="jsonl"),
        )

        class Backend:
            def complete(self, *, model, system, user, stage):
                return "compiled output"

        result = compile_migration(
            conversation,
            backend=Backend(),
            map_model="map",
            final_model="final",
            token_counter=counter,
        )
        self.assertEqual(result.report.tokenizer, "tiktoken:o200k_base")
        self.assertIs(result.report.tokenizer_exact, True)
        self.assertEqual(
            result.report.output_token_estimate,
            len("compiled output".encode("utf-8")),
        )


class _CliCounter:
    name = "tiktoken:o200k_base"
    exact = True

    def count(self, text):
        return len(text)


class _CliBackend:
    def complete(self, *, model, system, user, stage):
        return "compiled output"


class TiktokenCliTests(unittest.TestCase):
    def _source(self, root):
        source = root / "source.jsonl"
        source.write_text(
            json.dumps({"role": "user", "text": "question"})
            + "\n"
            + json.dumps({"role": "assistant", "text": "answer"})
            + "\n",
            encoding="utf-8",
        )
        return source

    def test_character_counter_rejects_tiktoken_only_options(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._source(root)
            stderr = io.StringIO()
            with mock.patch(
                "portable_ai_context.cli.create_backend", return_value=_CliBackend()
            ):
                with contextlib.redirect_stderr(stderr):
                    code = cli_main(
                        [
                            "compile",
                            str(source),
                            "-o",
                            str(root / "out"),
                            "--api-base",
                            "https://api.example.test/v1",
                            "--map-model",
                            "map-model",
                            "--final-model",
                            "final-model",
                            "--tiktoken-encoding",
                            "o200k_base",
                        ]
                    )
        self.assertEqual(code, 2)
        self.assertIn("require --token-counter tiktoken", stderr.getvalue())

    def test_tiktoken_defaults_model_lookup_to_final_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._source(root)
            with mock.patch(
                "portable_ai_context.cli.create_backend", return_value=_CliBackend()
            ), mock.patch(
                "portable_ai_context.cli.TiktokenTokenCounter",
                return_value=_CliCounter(),
            ) as counter:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = cli_main(
                        [
                            "compile",
                            str(source),
                            "-o",
                            str(root / "out"),
                            "--api-base",
                            "https://api.example.test/v1",
                            "--map-model",
                            "map-model",
                            "--final-model",
                            "final-model",
                            "--token-counter",
                            "tiktoken",
                        ]
                    )
        self.assertEqual(code, 0)
        counter.assert_called_once_with(encoding_name=None, model="final-model")

    def test_explicit_encoding_disables_model_lookup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._source(root)
            with mock.patch(
                "portable_ai_context.cli.create_backend", return_value=_CliBackend()
            ), mock.patch(
                "portable_ai_context.cli.TiktokenTokenCounter",
                return_value=_CliCounter(),
            ) as counter:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = cli_main(
                        [
                            "compile",
                            str(source),
                            "-o",
                            str(root / "out"),
                            "--api-base",
                            "https://api.example.test/v1",
                            "--map-model",
                            "map-model",
                            "--final-model",
                            "final-model",
                            "--token-counter",
                            "tiktoken",
                            "--tokenizer-model",
                            "ignored-model",
                            "--tiktoken-encoding",
                            "o200k_base",
                        ]
                    )
        self.assertEqual(code, 0)
        counter.assert_called_once_with(encoding_name="o200k_base", model=None)


if __name__ == "__main__":
    unittest.main()
