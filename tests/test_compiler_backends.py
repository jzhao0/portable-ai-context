import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from portable_ai_context.cli import main as cli_main
from portable_ai_context.compiler import (
    BackendConfig,
    CallableTokenCounter,
    OpenAICompatibleBackend,
    available_backends,
    compile_migration,
    create_backend,
    register_backend,
)
from portable_ai_context.errors import CompilerError
from _helpers import sample_conversation


class RecordingBackend:
    def __init__(self):
        self.calls = []

    def complete(self, *, model, system, user, stage):
        self.calls.append((stage, model, system, user))
        if stage == "map":
            return "checkpoint note " * 10
        if stage == "merge":
            return "merged"
        if stage == "budget":
            return "ok"
        return "one two three four five"


def exact_words():
    return CallableTokenCounter(
        fn=lambda text: len(text.split()),
        name="fake_exact_words",
        exact=True,
    )


class CompilerBackendRegistryTests(unittest.TestCase):
    def test_builtin_backend_is_discoverable_and_constructible(self):
        self.assertIn("openai-compatible", available_backends())
        config = BackendConfig(
            api_base="https://example.invalid/v1",
            api_key_env="TEST_BACKEND_KEY",
            timeout=17,
            environment={"TEST_BACKEND_KEY": "PRIVATE_API_KEY_VALUE"},
        )
        backend = create_backend("openai-compatible", config)
        self.assertIsInstance(backend, OpenAICompatibleBackend)
        self.assertEqual(backend.api_base, "https://example.invalid/v1")
        self.assertEqual(backend.timeout, 17)

    def test_backend_config_repr_does_not_expand_environment_or_options(self):
        config = BackendConfig(
            environment={"SECRET_ENV": "PRIVATE_ENV_VALUE"},
            options={"private_option": "PRIVATE_OPTION_VALUE"},
        )
        rendered = repr(config)
        self.assertNotIn("PRIVATE_ENV_VALUE", rendered)
        self.assertNotIn("PRIVATE_OPTION_VALUE", rendered)
        self.assertNotIn("SECRET_ENV", rendered)

    def test_registration_rejects_unsafe_name_and_duplicate(self):
        with self.assertRaisesRegex(ValueError, "safe lowercase identifier"):
            register_backend("../../PRIVATE_BACKEND", lambda config: RecordingBackend())

        name = "test-duplicate-backend"
        register_backend(name, lambda config: RecordingBackend())
        with self.assertRaisesRegex(ValueError, "already registered"):
            register_backend(name, lambda config: RecordingBackend())

    def test_unknown_backend_error_does_not_echo_untrusted_name(self):
        private_name = "PRIVATE_BACKEND_SECRET/../../x"
        with self.assertRaises(CompilerError) as caught:
            create_backend(private_name, BackendConfig())
        message = str(caught.exception)
        self.assertIn("unknown compiler backend", message)
        self.assertIn("openai-compatible", message)
        self.assertNotIn("PRIVATE_BACKEND_SECRET", message)

    def test_unexpected_factory_error_is_wrapped_without_detail(self):
        private_detail = "PRIVATE_FACTORY_DETAIL"
        name = "test-failing-backend"

        def fail(config):
            raise RuntimeError(private_detail)

        register_backend(name, fail)
        with self.assertRaises(CompilerError) as caught:
            create_backend(name, BackendConfig())
        self.assertEqual(str(caught.exception), "compiler backend construction failed")
        self.assertNotIn(private_detail, str(caught.exception))

    def test_openai_factory_validates_provider_specific_configuration(self):
        with self.assertRaisesRegex(CompilerError, "requires --api-base"):
            create_backend(
                "openai-compatible",
                BackendConfig(environment={"PAIC_API_KEY": "PRIVATE"}),
            )
        with self.assertRaisesRegex(CompilerError, "variable name is invalid"):
            create_backend(
                "openai-compatible",
                BackendConfig(
                    api_base="https://example.invalid/v1",
                    api_key_env="PRIVATE KEY NAME",
                    environment={},
                ),
            )

    def test_generic_pipeline_exercises_map_merge_final_and_budget_stages(self):
        backend = RecordingBackend()
        result = compile_migration(
            sample_conversation(),
            backend=backend,
            map_model="map-model",
            final_model="final-model",
            chunk_chars=40,
            reduce_chars=20,
            budget_tokens=1,
            token_counter=exact_words(),
        )
        stages = [stage for stage, _, _, _ in backend.calls]
        self.assertIn("map", stages)
        self.assertIn("merge", stages)
        self.assertIn("final", stages)
        self.assertEqual(stages[-1], "budget")
        self.assertEqual(result.final, "ok")
        self.assertTrue(result.report.budget_met)


class CompilerBackendCliTests(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        source = root / "compile.jsonl"
        source.write_text(
            json.dumps({"role": "user", "text": "compile question"})
            + "\n"
            + json.dumps({"role": "assistant", "text": "compile answer"})
            + "\n",
            encoding="utf-8",
        )
        return source

    def test_cli_default_backend_preserves_existing_openai_options(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._fixture(root)
            output = root / "out"
            backend = RecordingBackend()
            with mock.patch("portable_ai_context.cli.create_backend", return_value=backend) as create:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = cli_main(
                        [
                            "compile",
                            str(source),
                            "-o",
                            str(output),
                            "--api-base",
                            "https://example.invalid/v1",
                            "--api-key-env",
                            "CUSTOM_KEY",
                            "--timeout",
                            "17",
                            "--map-model",
                            "map",
                            "--final-model",
                            "final",
                        ]
                    )
            self.assertEqual(code, 0)
            backend_name, config = create.call_args.args
            self.assertEqual(backend_name, "openai-compatible")
            self.assertEqual(config.api_base, "https://example.invalid/v1")
            self.assertEqual(config.api_key_env, "CUSTOM_KEY")
            self.assertEqual(config.timeout, 17)
            self.assertIs(config.environment, os.environ)
            self.assertTrue((output / "MIGRATION_PROMPT.md").is_file())

    def test_cli_explicit_backend_is_forwarded_without_provider_hardcoding(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._fixture(root)
            backend = RecordingBackend()
            with mock.patch("portable_ai_context.cli.create_backend", return_value=backend) as create:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = cli_main(
                        [
                            "compile",
                            str(source),
                            "-o",
                            str(root / "out"),
                            "--backend",
                            "future-provider",
                            "--map-model",
                            "map",
                            "--final-model",
                            "final",
                        ]
                    )
            self.assertEqual(code, 0)
            self.assertEqual(create.call_args.args[0], "future-provider")

    def test_cli_unknown_backend_failure_is_content_safe(self):
        private_backend = "PRIVATE_BACKEND_SECRET/../../x"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = self._fixture(root)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = cli_main(
                    [
                        "compile",
                        str(source),
                        "-o",
                        str(root / "out"),
                        "--backend",
                        private_backend,
                        "--map-model",
                        "map",
                        "--final-model",
                        "final",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("unknown compiler backend", stderr.getvalue())
        self.assertIn("openai-compatible", stderr.getvalue())
        self.assertNotIn("PRIVATE_BACKEND_SECRET", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
